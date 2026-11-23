"""SAP master data (customer + material) for the order-intake accelerator — shared SQL builders.

`master_source = sap` resolves extracted orders against the real SAP masters instead of the demo templates.
Everything here returns SQL text (Spark SQL / Databricks SQL), so the SAME statements run in
  - `src/setup/01b_sap_masters.py`  (materializes the small `oi_sap_*` working tables), and
  - `src/pipeline/03_gold.py`       (resolves each order / line against them),
and in read-only validation (the materialization SELECTs inlined as CTEs over the SAP views).
No Spark import: the module is plain Python so it can be unit-tested locally.

SAP tables used (views `v_*` = one row per key; `c_*` change logs are NOT used):
  KNA1 v_customer_master, ADRC v_address_master_customer, KNVV v_customer_sales_org_master,
  KNVP v_customer_master_partner_functions, MARA v_material_master, MARM v_material_master_unit_of_measures,
  MAKT v_material_text, MVKE v_material_master_sales, t_sales_org_geography_look_up.
"""
import re
import unicodedata

SAP_SCHEMA = "db_fnd_proc"
DEFAULT_CLIENT = "100"
SALEABLE_MTART = ("FERT", "HAWA")              # finished products, trading goods
LINK_PARVW = ("AG", "WE", "RE", "RG")          # sold-to, ship-to, bill-to, payer (German SAP codes)
# Working tables in the accelerator's schema (prefixed: the schema may be shared with other accelerators).
T_CUSTOMERS = "oi_sap_customers"
T_LINKS = "oi_sap_partner_links"
T_MATERIALS = "oi_sap_materials"
T_REGIONS = "oi_sap_region_map"
T_PO_RULES = "po_rules"

# Words that don't identify a customer (legal forms, articles). Removed after normalization.
LEGAL_WORDS = (
    "gmbh", "mbh", "ag", "kg", "co", "ohg", "ug", "ek", "ev", "gesmbh", "kgaa",
    "sas", "sarl", "sa", "srl", "sl", "spa", "snc", "selas", "eurl",
    "bv", "nv", "vof", "ltd", "limited", "inc", "llc", "plc", "cie", "und", "and", "the", "et",
)
# Trade words that say what a customer is, not which one ('Parfümerie Muster & Sohn' = SAP 'MUSTER & SOHN').
# Ignored on the order side of the word-overlap score only.
GENERIC_WORDS = (
    "parfuemerie", "parfumerie", "parfumeri", "parfum", "parfums", "drogerie", "drogisterij", "apotheke", "apotheek",
    "pharmacie", "farmacia", "friseur", "coiffeur", "coiffure", "kapsalon", "salon", "haarstudio", "studio",
    "kosmetik", "kosmetikstudio", "cosmetics", "cosmetic", "beauty", "beaute", "store", "shop", "shops",
    "boutique", "btq", "institut",
)
# German transliteration first (Müller == Mueller), then plain accents.
_TRANSLIT = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"))
_ACCENTS = {
    "á": "a", "à": "a", "â": "a", "ã": "a", "å": "a", "ā": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e", "ē": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i",
    "ó": "o", "ò": "o", "ô": "o", "õ": "o", "ø": "o",
    "ú": "u", "ù": "u", "û": "u", "ç": "c", "ñ": "n",
}

# Customer match thresholds (see customer_resolution_sql).
AMBIGUITY_MARGIN = 0.05


# ---------------------------------------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------------------------------------
def parse_sales_orgs(value):
    """'4160, 4020,4160' -> ['4160', '4020'] (order kept: the first listed org is preferred on ties)."""
    out = []
    for part in str(value or "").split(","):
        p = part.strip()
        if not p:
            continue
        if not re.fullmatch(r"[A-Za-z0-9]{1,4}", p):
            raise ValueError(f"invalid sales org {p!r} (expected up to 4 letters/digits)")
        if p not in out:
            out.append(p)
    if not out:
        raise ValueError("sap_sales_orgs is empty")
    return out


def parse_prefix_len(value):
    n = int(str(value).strip() or 6)
    if not 4 <= n <= 18:
        raise ValueError(f"material_prefix_len must be 4..18, got {n}")
    return n


def check_identifier(name, what="catalog"):
    if not re.fullmatch(r"[A-Za-z0-9_]+", str(name or "")):
        raise ValueError(f"invalid {what} name {name!r}")
    return name


def check_client(client):
    if not re.fullmatch(r"[0-9]{3}", str(client)):
        raise ValueError(f"invalid SAP client {client!r}")
    return client


def sql_list(values):
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def sap_table(catalog, name):
    return f"`{check_identifier(catalog)}`.`{SAP_SCHEMA}`.`{name}`"


# ---------------------------------------------------------------------------------------------------------
# normalization — SQL expressions + pure-Python mirrors (unit-tested against each other)
# ---------------------------------------------------------------------------------------------------------
def norm_text_sql(expr):
    """lower, German transliteration, accents stripped, every non [a-z0-9] run -> one space, trimmed."""
    s = f"lower(coalesce({expr}, ''))"
    for a, b in _TRANSLIT:
        s = f"replace({s}, '{a}', '{b}')"
    src, dst = "".join(_ACCENTS), "".join(_ACCENTS.values())
    s = f"translate({s}, '{src}', '{dst}')"
    return f"trim(regexp_replace({s}, '[^a-z0-9]+', ' '))"


def norm_text(s):
    t = str(s or "").lower()
    for a, b in _TRANSLIT:
        t = t.replace(a, b)
    t = "".join(_ACCENTS.get(c, c) for c in t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_LEGAL_RE_SQL = "(" + "|".join(LEGAL_WORDS) + ")"


def norm_name_sql(expr):
    """norm_text + legal forms/articles removed: 'Parfümerie Muster GmbH' -> 'parfuemerie muster'."""
    t = norm_text_sql(expr)
    # pad with spaces; a word is ' word' followed by a space (lookahead keeps the space for the next word)
    s = f"regexp_replace(concat(' ', {t}, ' '), ' {_LEGAL_RE_SQL}(?= )', ' ')"
    return f"trim(regexp_replace({s}, ' +', ' '))"


def norm_name(s):
    t = f" {norm_text(s)} "
    t = re.sub(rf" {_LEGAL_RE_SQL}(?= )", " ", t)
    return re.sub(r" +", " ", t).strip()


def street_key_sql(expr):
    """Street name for matching: the text before the first digit, 'strasse'/'straße' -> 'str'.
    'Musterstrasse 16-20/Hof' -> 'musterstr'."""
    return f"trim(regexp_replace({norm_text_sql(f'regexp_extract({expr}, {chr(39)}^[^0-9]*{chr(39)}, 0)')}, 'strasse', 'str'))"


def street_key(s):
    m = re.match(r"^[^0-9]*", str(s or ""))
    return norm_text(m.group(0)).replace("strasse", "str").strip()


def street_text_sql(expr):
    """The order text normalized the same way as street keys (so 'Kärntner Straße 19' contains 'kaerntner str')."""
    return f"regexp_replace({norm_text_sql(expr)}, 'strasse', 'str')"


def code_norm_sql(expr):
    """Material / EAN as printed -> upper alphanumerics: '081 6164' -> '0816164'."""
    return f"upper(regexp_replace(coalesce({expr}, ''), '[^A-Za-z0-9]', ''))"


def code_norm(s):
    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).upper()


def ean_key_sql(expr):
    """EAN/UPC compared without leading zeros (UPC-12 printed as 13 digits, EAN stored with/without zero)."""
    return f"regexp_replace({expr}, '^0+', '')"


def material_prefix(code, n=6):
    """Pure-Python mirror of the prefix rule used in material_resolution_sql (for tests/docs)."""
    c = code_norm(code)
    if len(c) < n or re.fullmatch(r"[0-9]{12,14}", c):
        return None
    return c[:n]


def name_similarity(a, b):
    """1 - levenshtein / max length (mirror of _sim_sql)."""
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


def _sim_sql(a, b):
    return (f"CASE WHEN {a} = '' OR {b} = '' THEN 0.0 "
            f"ELSE 1.0 - levenshtein({a}, {b}) / greatest(length({a}), length({b})) END")


def _overlap_sql(tokens_of, words):
    """Share of the order-name words (>= 3 chars, trade words ignored; at least two) found among `words` (array of
    the candidate's name + city words)."""
    t = f"filter(split({tokens_of}, ' '), x -> length(x) >= 3 AND NOT array_contains(array({sql_list(GENERIC_WORDS)}), x))"
    # needs two distinctive words: one shared word ('Alpha') is what every store of a chain has in common
    return (f"CASE WHEN size(array_distinct({t})) < 2 THEN 0.0 "
            f"ELSE size(array_intersect({t}, {words})) / size(array_distinct({t})) END")


def _contains_word_sql(hay, needle, min_len=5):
    """needle appears in hay as whole words (both normalized, space separated)."""
    return (f"(length({needle}) >= {min_len} AND "
            f"instr(concat(' ', {hay}, ' '), concat(' ', {needle}, ' ')) > 0)")


# ---------------------------------------------------------------------------------------------------------
# materialization (01b_sap_masters.py): small working tables, restricted to the configured sales orgs
# ---------------------------------------------------------------------------------------------------------
def customers_select(catalog, sales_orgs, client=DEFAULT_CLIENT):
    """One row per (customer, sales org) with a KNVV sales view in the configured orgs: name, address
    (KNA1 + ADRC street line 2), country, currency (KNVV.WAERS), deletion/block flags, sold-to/ship-to role,
    and normalized match keys."""
    cl, orgs = check_client(client), sql_list(sales_orgs)
    t = lambda n: sap_table(catalog, n)  # noqa: E731
    return f"""
WITH knvv_cur AS (
  SELECT KUNNR, VKORG, WAERS, count(*) n,
         sum(CASE WHEN coalesce(LOEVM, '') <> 'X' THEN 1 ELSE 0 END) n_live,
         max(CASE WHEN coalesce(AUFSD, '') <> '' THEN 1 ELSE 0 END) blocked
  FROM {t('v_customer_sales_org_master')}
  WHERE MANDT = '{cl}' AND VKORG IN ({orgs})
  GROUP BY KUNNR, VKORG, WAERS
),
knvv AS (
  SELECT KUNNR kunnr, VKORG sales_org,
         max_by(nullif(WAERS, ''), struct(n_live, n, WAERS)) currency,
         count(DISTINCT nullif(WAERS, '')) n_currencies,
         sum(n_live) = 0 sales_org_deleted,
         max(blocked) = 1 sales_org_order_block
  FROM knvv_cur GROUP BY KUNNR, VKORG
),
links AS (
  SELECT DISTINCT KUNNR, VKORG, PARVW, KUNN2
  FROM {t('v_customer_master_partner_functions')}
  WHERE MANDT = '{cl}' AND VKORG IN ({orgs}) AND PARVW IN ('AG', 'WE')
),
sold AS (SELECT DISTINCT KUNNR kunnr, VKORG sales_org FROM links WHERE PARVW = 'AG' AND KUNN2 = KUNNR),
ship AS (SELECT DISTINCT KUNN2 kunnr, VKORG sales_org FROM links WHERE PARVW = 'WE'),
base AS (
  SELECT v.kunnr, v.sales_org, v.currency, v.n_currencies, v.sales_org_deleted, v.sales_org_order_block,
         k.NAME1 name1, nullif(k.NAME2, '') name2, nullif(k.NAME3, '') name3,
         coalesce(nullif(trim(concat_ws(' ', nullif(a.STREET, ''), nullif(a.HOUSE_NUM1, ''))), ''), nullif(k.STRAS, '')) street,
         nullif(concat_ws(', ', nullif(a.STR_SUPPL1, ''), nullif(a.STR_SUPPL2, ''), nullif(a.STR_SUPPL3, ''),
                          nullif(a.LOCATION, ''), nullif(a.BUILDING, ''), nullif(a.FLOOR, ''),
                          nullif(a.ROOMNUMBER, ''), nullif(a.HOUSE_NUM2, '')), '') street2,
         coalesce(nullif(k.PSTLZ, ''), nullif(a.POST_CODE1, '')) postcode,
         coalesce(nullif(k.ORT01, ''), nullif(a.CITY1, '')) city,
         k.LAND1 country, k.KTOKD account_group,
         coalesce(k.LOEVM, '') = 'X' customer_deleted,
         coalesce(k.AUFSD, '') <> '' customer_order_block,
         s.kunnr IS NOT NULL is_sold_to, w.kunnr IS NOT NULL is_ship_to
  FROM knvv v
  JOIN {t('v_customer_master')} k ON k.MANDT = '{cl}' AND k.KUNNR = v.kunnr
  LEFT JOIN {t('v_address_master_customer')} a
    ON a.CLIENT = '{cl}' AND a.ADDRNUMBER = k.ADRNR AND coalesce(a.NATION, '') = ''
  LEFT JOIN sold s ON s.kunnr = v.kunnr AND s.sales_org = v.sales_org
  LEFT JOIN ship w ON w.kunnr = v.kunnr AND w.sales_org = v.sales_org
),
n AS (
  SELECT *,
    {norm_name_sql("concat_ws(' ', name1, name2)")} name_norm,
    {norm_name_sql('name1')} name1_norm,
    {street_key_sql('street')} street_key,
    {norm_text_sql('postcode')} postcode_key,
    {norm_text_sql('city')} city_norm
  FROM base
)
SELECT *,
  coalesce(element_at(split(city_norm, ' '), 1), '') city_key,
  array_distinct(filter(concat(split(name_norm, ' '), split(postcode_key, ' ')), x -> length(x) >= 4)) match_tokens
FROM n"""


def partner_links_select(catalog, sales_orgs, client=DEFAULT_CLIENT):
    """KNVP: sold-to -> partner per sales org (AG/WE/RE/RG), distribution channel/division collapsed."""
    return f"""
SELECT VKORG sales_org, KUNNR sold_to, PARVW parvw, KUNN2 partner, count(*) n_views
FROM {sap_table(catalog, 'v_customer_master_partner_functions')}
WHERE MANDT = '{check_client(client)}' AND VKORG IN ({sql_list(sales_orgs)}) AND PARVW IN ({sql_list(LINK_PARVW)})
  AND coalesce(KUNN2, '') <> ''
GROUP BY VKORG, KUNNR, PARVW, KUNN2"""


def materials_select(catalog, sales_orgs, prefix_len=6, client=DEFAULT_CLIENT):
    """One row per saleable material (MTART FERT/HAWA) listed (MVKE) in a configured sales org: prefix,
    EANs (MARA + MARM, leading zeros dropped), German/English text, listed sales orgs + sales status (shown,
    never filtered on)."""
    cl, orgs, n = check_client(client), sql_list(sales_orgs), parse_prefix_len(prefix_len)
    t = lambda x: sap_table(catalog, x)  # noqa: E731
    return f"""
WITH mvke AS (
  SELECT MATNR, sort_array(collect_set(VKORG)) sales_orgs,
         sort_array(collect_set(nullif(concat(VKORG, ':', coalesce(VMSTA, '')), concat(VKORG, ':')))) sales_status
  FROM {t('v_material_master_sales')}
  WHERE MANDT = '{cl}' AND VKORG IN ({orgs})
  GROUP BY MATNR
),
mara AS (
  SELECT m.MATNR matnr, m.MTART mtart, m.MATKL matkl, m.MEINS base_uom, coalesce(m.LVORM, '') = 'X' deleted,
         {ean_key_sql("trim(coalesce(m.EAN11, ''))")} ean_mara, v.sales_orgs, v.sales_status
  FROM {t('v_material_master')} m JOIN mvke v ON v.MATNR = m.MATNR
  WHERE m.MANDT = '{cl}' AND m.MTART IN ({sql_list(SALEABLE_MTART)})
),
marm AS (
  SELECT u.MATNR, collect_set({ean_key_sql("trim(u.EAN11)")}) eans
  FROM {t('v_material_master_unit_of_measures')} u JOIN mara ON mara.matnr = u.MATNR
  WHERE u.MANDT = '{cl}' AND coalesce(trim(u.EAN11), '') <> ''
  GROUP BY u.MATNR
),
makt AS (
  SELECT x.MATNR, max(CASE WHEN x.SPRAS = 'D' THEN x.MAKTX END) text_de, max(CASE WHEN x.SPRAS = 'E' THEN x.MAKTX END) text_en
  FROM {t('v_material_text')} x JOIN mara ON mara.matnr = x.MATNR
  WHERE x.MANDT = '{cl}' AND x.SPRAS IN ('D', 'E')
  GROUP BY x.MATNR
)
SELECT mara.matnr,
  CASE WHEN mara.matnr RLIKE '^[0-9]+$' THEN NULL ELSE substr(mara.matnr, 1, {n}) END prefix,
  mara.mtart, mara.matkl, mara.base_uom, mara.deleted,
  array_distinct(filter(concat(array(mara.ean_mara), coalesce(marm.eans, array())), x -> x <> '')) eans,
  makt.text_de, makt.text_en, mara.sales_orgs, mara.sales_status
FROM mara
LEFT JOIN marm ON marm.MATNR = mara.matnr
LEFT JOIN makt ON makt.MATNR = mara.matnr"""


def region_map_select(catalog, sales_orgs):
    """t_sales_org_geography_look_up -> (sales org, country) -> affiliate / market / DP region / area.
    The look-up keeps versions (CDC_CODE I/U/D): latest row per key, deletions dropped; the most common
    affiliate across divisions wins."""
    t = sap_table(catalog, "t_sales_org_geography_look_up")
    return f"""
WITH g AS (
  SELECT COUNTRY country, `/BIC/ZGEOGRPHY` sales_org, `/BIC/ZAFFLIATE` affiliate, `/BIC/ZRMARKET` market,
         `/BIC/ZDPREGION` dp_region, `/BIC/ZAREA` area, CDC_CODE,
         ROW_NUMBER() OVER (PARTITION BY COUNTRY, `/BIC/ZGEOGRPHY`, DIVISION, PLANT ORDER BY LOAD_TS DESC) rn
  FROM {t}
  WHERE coalesce(OBJVERS, 'A') = 'A' AND `/BIC/ZGEOGRPHY` IN ({sql_list(sales_orgs)})
),
c AS (
  SELECT sales_org, country, affiliate, market, dp_region, area, count(*) n
  FROM g WHERE rn = 1 AND coalesce(CDC_CODE, '') <> 'D' AND coalesce(affiliate, '') <> ''
  GROUP BY ALL
)
SELECT sales_org, country,
  max_by(affiliate, struct(n, affiliate)) affiliate, max_by(market, struct(n, affiliate)) market,
  max_by(dp_region, struct(n, affiliate)) dp_region, max_by(area, struct(n, affiliate)) area
FROM c GROUP BY sales_org, country"""


PO_RULES_DDL = """(
  sold_to STRING, rule STRING, pattern STRING
) COMMENT 'Per-customer missing/invalid PO handling (master_source=sap). rule = require (default for every customer: a missing PO is flagged; pattern = optional regex the PO must match) | generate (a missing PO gets a reference from pattern; tokens {date} = received yyyyMMdd, {doc} = 6-char document hash; default AUTO-{date}-{doc}). sold_to = 10-digit SAP customer number. Empty until the business fills it.'"""


def materialize_statements(schema_fqn, catalog, sales_orgs, prefix_len=6, client=DEFAULT_CLIENT):
    """(table, statement) pairs run by 01b_sap_masters.py. Working tables are replaced each run; po_rules is
    created once and never overwritten."""
    return [
        (T_CUSTOMERS, f"CREATE OR REPLACE TABLE {schema_fqn}.{T_CUSTOMERS} "
                      f"COMMENT 'SAP customers (KNA1+ADRC+KNVV) with a sales view in the configured sales orgs — "
                      f"working copy for order resolution, refreshed by 01b_sap_masters' AS {customers_select(catalog, sales_orgs, client)}"),
        (T_LINKS, f"CREATE OR REPLACE TABLE {schema_fqn}.{T_LINKS} "
                  f"COMMENT 'SAP partner functions (KNVP AG/WE/RE/RG) for the configured sales orgs' AS {partner_links_select(catalog, sales_orgs, client)}"),
        (T_MATERIALS, f"CREATE OR REPLACE TABLE {schema_fqn}.{T_MATERIALS} "
                      f"COMMENT 'Saleable SAP materials (MARA FERT/HAWA + MARM EANs + MAKT) listed (MVKE) in the configured sales orgs' "
                      f"AS {materials_select(catalog, sales_orgs, prefix_len, client)}"),
        (T_REGIONS, f"CREATE OR REPLACE TABLE {schema_fqn}.{T_REGIONS} "
                    f"COMMENT 'SAP sales org + country -> affiliate/market/region (t_sales_org_geography_look_up)' AS {region_map_select(catalog, sales_orgs)}"),
        (T_PO_RULES, f"CREATE TABLE IF NOT EXISTS {schema_fqn}.{T_PO_RULES} {PO_RULES_DDL}"),
    ]


# ---------------------------------------------------------------------------------------------------------
# customer resolution
# ---------------------------------------------------------------------------------------------------------
def customer_resolution_sql(orders, customers, links, sales_orgs, overrides=None, max_token_df=3000):
    """Resolve each order's customer to an SAP sold-to (+ ship-to, sales org, currency).

    orders:    relation with doc_id, order_idx, customer_name, customer_number, ship_to, customer_is_supplier
    customers: oi_sap_customers (or its SELECT as a CTE); links: oi_sap_partner_links
    overrides: optional customer_master (name_variant -> sap_sold_to) — pinned variants win when the pinned
               sold-to exists in `customers`.
    One output row per (doc_id, order_idx).

    Evidence per candidate (only candidates sharing a name/postcode token, or the printed customer number):
      name_sim  normalized name similarity (Levenshtein, or whole-word containment = 0.9)
      address   postcode 0.40 + city 0.25 + street 0.35, found in customer name + ship-to text
      number    the document's customer number (zero-padded) = KUNNR, accepted only with some name or address
                evidence (name_sim >= 0.5, the order name inside the SAP name, or address >= 0.4)
    A candidate is acceptable by: number | name >= 0.6 and address >= 0.4 | name >= 0.85 | address >= 0.75 and
    name >= 0.35. score = 0.6 name + 0.4 address (+0.3 number). A ship-to-only candidate maps to its sold-to(s)
    through KNVP WE. Two different sold-tos within AMBIGUITY_MARGIN of the best -> ambiguous (not picked).
    """
    org_arr = f"array({sql_list(sales_orgs)})"
    m = AMBIGUITY_MARGIN
    ov = ""
    ov_join = ""
    ov_cols = "CAST(NULL AS STRING) pinned_sold_to, CAST(NULL AS BOOLEAN) pinned_in_sap"
    if overrides:
        ov = f""",
ovc AS (
  SELECT o.doc_id, o.order_idx, lpad(trim(c.sap_sold_to), 10, '0') pinned,
    ROW_NUMBER() OVER (PARTITION BY o.doc_id, o.order_idx ORDER BY
      CASE WHEN o.cn_demo = c.nv THEN 1.0 ELSE 1.0 - levenshtein(o.cn_demo, c.nv) / greatest(length(o.cn_demo), length(c.nv), 1) END DESC) rn,
    CASE WHEN o.cn_demo = c.nv THEN 1.0 ELSE 1.0 - levenshtein(o.cn_demo, c.nv) / greatest(length(o.cn_demo), length(c.nv), 1) END s
  FROM o CROSS JOIN (SELECT sap_sold_to, lower(regexp_replace(name_variant, '[^A-Za-z0-9 ]', '')) nv FROM {overrides}
                     WHERE coalesce(trim(sap_sold_to), '') <> '') c
  WHERE NOT o.is_supplier
),
ov AS (
  SELECT ovc.doc_id, ovc.order_idx, ovc.pinned,
    EXISTS (SELECT 1 FROM cust WHERE cust.kunnr = ovc.pinned AND cust.is_sold_to) pinned_in_sap
  FROM ovc WHERE rn = 1 AND s >= 0.85
)"""
        ov_join = "LEFT JOIN ov ON ov.doc_id = o.doc_id AND ov.order_idx = o.order_idx"
        ov_cols = "ov.pinned pinned_sold_to, ov.pinned_in_sap"
    return f"""
WITH o AS (
  SELECT doc_id, order_idx, customer_name, ship_to,
    coalesce(customer_is_supplier, false) is_supplier,
    lower(regexp_replace(customer_name, '[^A-Za-z0-9 ]', '')) cn_demo,
    {norm_name_sql('customer_name')} o_name,
    {norm_name_sql('ship_to')} o_ship_name,
    {street_text_sql("concat_ws(' ', customer_name, ship_to)")} o_text,
    {street_text_sql('ship_to')} o_ship_text,
    CASE WHEN customer_number NOT RLIKE '[A-Za-z]'
              AND length(regexp_replace(customer_number, '[^0-9]', '')) BETWEEN 4 AND 10
         THEN lpad(regexp_replace(customer_number, '[^0-9]', ''), 10, '0') END o_number
  FROM {orders}
),
cust AS (SELECT * FROM {customers}),
tok_df AS (SELECT tok, count(*) df FROM cust LATERAL VIEW explode(match_tokens) t AS tok GROUP BY tok),
cust_tok AS (
  SELECT DISTINCT x.kunnr, x.tok
  FROM (SELECT c.kunnr, tok FROM cust c LATERAL VIEW explode(c.match_tokens) t AS tok) x
  JOIN tok_df d ON d.tok = x.tok AND d.df <= {int(max_token_df)}
),
o_tok AS (
  SELECT DISTINCT doc_id, order_idx, tok
  FROM o LATERAL VIEW explode(filter(split(concat_ws(' ', o_name, o_ship_name, o_text), ' '), x -> length(x) >= 4)) t AS tok
  WHERE NOT is_supplier
),
pairs AS (
  SELECT DISTINCT ot.doc_id, ot.order_idx, ct.kunnr FROM o_tok ot JOIN cust_tok ct ON ct.tok = ot.tok
  UNION
  SELECT o.doc_id, o.order_idx, c.kunnr FROM o JOIN cust c ON c.kunnr = o.o_number WHERE NOT o.is_supplier
),
ev AS (
  SELECT o.doc_id, o.order_idx, c.*, o.o_number,
    greatest({_sim_sql('o.o_name', 'c.name_norm')}, {_sim_sql('o.o_name', 'c.name1_norm')},
             -- the order's name inside the SAP name ('Le Muster' in 'Parfuemerie Le Muster'); the other way round
             -- only via the word overlap (each extra order word must be a SAP name/city word: 'Muster Nordstadt')
             -- (a single short word inside a long SAP name is too weak: 'Muster' in 'Salon Peter Muster Haare')
             CASE WHEN {_contains_word_sql('c.name_norm', 'o.o_name')}
                       AND (instr(o.o_name, ' ') > 0 OR length(o.o_name) >= 0.4 * length(c.name_norm)) THEN 0.9 ELSE 0.0 END,
             0.9 * {_overlap_sql('o.o_name', "split(concat_ws(' ', c.name_norm, c.city_norm), ' ')")}) name_sim,
    {_contains_word_sql('c.name_norm', 'o.o_name', 3)} name_contained,
    greatest({_sim_sql('o.o_ship_name', 'c.name_norm')}, {_sim_sql('o.o_ship_name', 'c.name1_norm')},
             CASE WHEN {_contains_word_sql('o.o_ship_text', 'c.name1_norm')} THEN 0.9 ELSE 0.0 END) ship_name_sim,
    (c.postcode_key <> '' AND instr(concat(' ', o.o_text, ' '), concat(' ', c.postcode_key, ' ')) > 0) pc_hit,
    (length(c.city_key) >= 3 AND instr(concat(' ', o.o_text, ' '), concat(' ', c.city_key, ' ')) > 0) city_hit,
    (length(c.street_key) >= 5 AND instr(o.o_text, c.street_key) > 0) street_hit,
    (c.postcode_key <> '' AND instr(concat(' ', o.o_ship_text, ' '), concat(' ', c.postcode_key, ' ')) > 0) pc_hit_ship,
    (length(c.city_key) >= 3 AND instr(concat(' ', o.o_ship_text, ' '), concat(' ', c.city_key, ' ')) > 0) city_hit_ship,
    (length(c.street_key) >= 5 AND instr(o.o_ship_text, c.street_key) > 0) street_hit_ship,
    (c.kunnr = o.o_number) number_hit,
    array_position({org_arr}, c.sales_org) org_rank
  FROM pairs p
  JOIN o ON o.doc_id = p.doc_id AND o.order_idx = p.order_idx
  JOIN cust c ON c.kunnr = p.kunnr
),
sc AS (
  SELECT *,
    0.4 * CAST(pc_hit AS INT) + 0.25 * CAST(city_hit AS INT) + 0.35 * CAST(street_hit AS INT) addr,
    0.4 * CAST(pc_hit_ship AS INT) + 0.25 * CAST(city_hit_ship AS INT) + 0.35 * CAST(street_hit_ship AS INT) addr_ship
  FROM ev
),
acc AS (
  SELECT *,
    CASE WHEN number_hit AND (name_sim >= 0.5 OR addr >= 0.4 OR name_contained) THEN 'customer_number'
         WHEN name_sim >= 0.6 AND addr >= 0.4 THEN 'name_address'
         WHEN name_sim >= 0.85 THEN 'name'
         WHEN addr >= 0.75 AND name_sim >= 0.35 THEN 'address' END method,
    0.6 * name_sim + 0.4 * addr + CASE WHEN number_hit AND (name_sim >= 0.5 OR addr >= 0.4 OR name_contained)
                                       THEN 0.3 ELSE 0.0 END
      - CASE WHEN customer_deleted OR sales_org_deleted THEN 0.1 ELSE 0.0 END
      - CASE WHEN customer_order_block OR sales_org_order_block THEN 0.06 ELSE 0.0 END score
  FROM sc
),
-- sold-to candidates: acceptable customers that are sold-tos. Only when an order has none: the sold-to(s) whose
-- ship-to / bill-to / payer (KNVP WE/RE/RG) the matched customer is (e.g. the order names the paying company).
direct AS (
  SELECT a.doc_id, a.order_idx, a.kunnr sold_to, a.sales_org, a.method, a.score, a.org_rank, false via_partner,
         a.kunnr matched_kunnr, CAST(NULL AS STRING) via_parvw
  FROM acc a WHERE a.method IS NOT NULL AND a.is_sold_to
),
st AS (
  SELECT * FROM direct
  UNION ALL
  SELECT a.doc_id, a.order_idx, l.sold_to, a.sales_org, a.method, a.score - 0.01, a.org_rank, true, a.kunnr, l.parvw
  FROM acc a
  JOIN {links} l ON l.partner = a.kunnr AND l.sales_org = a.sales_org AND l.parvw IN ('WE', 'RE', 'RG')
                AND l.sold_to <> a.kunnr
  JOIN cust s ON s.kunnr = l.sold_to AND s.sales_org = l.sales_org AND s.is_sold_to
  LEFT ANTI JOIN direct d ON d.doc_id = a.doc_id AND d.order_idx = a.order_idx
  WHERE a.method IS NOT NULL AND NOT a.is_sold_to
),
st1 AS (   -- best evidence per (order, sold-to): highest score, then the first configured sales org
  SELECT * FROM (
    SELECT st.*, ROW_NUMBER() OVER (PARTITION BY doc_id, order_idx, sold_to
                                    ORDER BY score DESC, via_partner, org_rank) r FROM st) WHERE r = 1
),
ranked AS (
  SELECT st1.*,
    ROW_NUMBER() OVER (PARTITION BY doc_id, order_idx ORDER BY score DESC, org_rank, sold_to) rk,
    max(score) OVER (PARTITION BY doc_id, order_idx) best
  FROM st1
),
amb AS (
  SELECT doc_id, order_idx,
    count(CASE WHEN score >= best - {m} THEN 1 END) n_close,
    slice(transform(array_sort(collect_list(CASE WHEN score >= best - {m} THEN struct(-score AS k, sold_to AS s) END)),
                    x -> x.s), 1, 5) close_sold_tos
  FROM ranked GROUP BY doc_id, order_idx
){ov},
pick AS (
  SELECT o.doc_id, o.order_idx, o.is_supplier, o.ship_to, o.o_ship_name, o.o_ship_text,
    {ov_cols},
    r.sold_to auto_sold_to, r.sales_org auto_org, r.method auto_method, r.score auto_score, r.via_partner, r.via_parvw,
    r.matched_kunnr, coalesce(a.n_close, 0) n_close, a.close_sold_tos
  FROM o
  LEFT JOIN ranked r ON r.doc_id = o.doc_id AND r.order_idx = o.order_idx AND r.rk = 1
  LEFT JOIN amb a ON a.doc_id = o.doc_id AND a.order_idx = o.order_idx
  {ov_join}
),
res AS (
  SELECT p.*,
    CASE WHEN p.is_supplier THEN NULL
         WHEN p.pinned_in_sap THEN p.pinned_sold_to
         WHEN p.n_close = 1 THEN p.auto_sold_to END sap_sold_to,
    CASE WHEN p.is_supplier THEN 'none'
         WHEN p.pinned_in_sap THEN 'name_variant'
         WHEN p.n_close > 1 THEN 'ambiguous'
         WHEN p.n_close = 1 THEN p.auto_method ELSE 'none' END customer_match_method
  FROM pick p
),
-- sales org for the chosen sold-to: the matched org, else (pinned) the first configured org it has a view in
org AS (
  SELECT r.doc_id, r.order_idx, c.sales_org, c.currency, c.n_currencies, c.country, c.name1,
         c.customer_deleted OR c.sales_org_deleted deleted, c.customer_order_block OR c.sales_org_order_block blocked,
         ROW_NUMBER() OVER (PARTITION BY r.doc_id, r.order_idx ORDER BY
           CASE WHEN c.sales_org = r.auto_org AND r.customer_match_method <> 'name_variant' THEN 0 ELSE 1 END,
           array_position({org_arr}, c.sales_org)) rn,
         count(*) OVER (PARTITION BY r.doc_id, r.order_idx) n_orgs
  FROM res r JOIN cust c ON c.kunnr = r.sap_sold_to
),
-- ship-to: a WE partner of the sold-to in its sales org, else any SAP ship-to (-> not linked)
sh AS (
  SELECT r.doc_id, r.order_idx, a.kunnr ship_kunnr,
    (l.partner IS NOT NULL) linked,
    0.4 * a.ship_name_sim + 0.6 * a.addr_ship ship_score,
    (a.addr_ship >= 0.4 OR a.ship_name_sim >= 0.85) ship_ok
  FROM res r
  JOIN org g ON g.doc_id = r.doc_id AND g.order_idx = r.order_idx AND g.rn = 1
  JOIN acc a ON a.doc_id = r.doc_id AND a.order_idx = r.order_idx AND a.is_ship_to
  LEFT JOIN {links} l ON l.sold_to = r.sap_sold_to AND l.partner = a.kunnr AND l.parvw = 'WE' AND l.sales_org = g.sales_org
  WHERE coalesce(trim(r.ship_to), '') <> ''
),
sh_linked AS (   -- linked ship-tos the token search did not reach (e.g. address-only ship-to text)
  SELECT r.doc_id, r.order_idx, c.kunnr ship_kunnr, true linked,
    0.6 * (0.4 * CAST(c.postcode_key <> '' AND instr(concat(' ', r.o_ship_text, ' '), concat(' ', c.postcode_key, ' ')) > 0 AS INT)
         + 0.25 * CAST(length(c.city_key) >= 3 AND instr(concat(' ', r.o_ship_text, ' '), concat(' ', c.city_key, ' ')) > 0 AS INT)
         + 0.35 * CAST(length(c.street_key) >= 5 AND instr(r.o_ship_text, c.street_key) > 0 AS INT)) ship_score
  FROM res r
  JOIN org g ON g.doc_id = r.doc_id AND g.order_idx = r.order_idx AND g.rn = 1
  JOIN {links} l ON l.sold_to = r.sap_sold_to AND l.parvw = 'WE' AND l.sales_org = g.sales_org
  JOIN cust c ON c.kunnr = l.partner AND c.sales_org = g.sales_org
  WHERE coalesce(trim(r.ship_to), '') <> ''
),
sh_all AS (
  SELECT doc_id, order_idx, ship_kunnr, linked, ship_score FROM sh WHERE ship_ok
  UNION ALL
  SELECT doc_id, order_idx, ship_kunnr, linked, ship_score FROM sh_linked WHERE ship_score >= 0.24
),
sh_best AS (
  SELECT * FROM (
    SELECT sh_all.*, ROW_NUMBER() OVER (PARTITION BY doc_id, order_idx
                                        ORDER BY linked DESC, ship_score DESC, ship_kunnr) rn FROM sh_all) WHERE rn = 1
),
n_we AS (   -- how many ship-tos the sold-to has (one = the sold-to itself is the only delivery address)
  SELECT r.doc_id, r.order_idx, count(DISTINCT l.partner) n, max(l.partner) only_partner
  FROM res r JOIN org g ON g.doc_id = r.doc_id AND g.order_idx = r.order_idx AND g.rn = 1
  JOIN {links} l ON l.sold_to = r.sap_sold_to AND l.parvw = 'WE' AND l.sales_org = g.sales_org
  GROUP BY r.doc_id, r.order_idx
)
SELECT r.doc_id, r.order_idx, r.sap_sold_to, g.name1 sap_sold_to_name, g.sales_org sap_sales_org, g.currency sap_currency,
  g.n_currencies sap_n_currencies, g.country sap_country, coalesce(g.deleted, false) sap_customer_deleted,
  coalesce(g.blocked, false) sap_customer_blocked, g.n_orgs sap_n_sales_orgs,
  r.customer_match_method,
  CASE WHEN r.customer_match_method = 'name_variant' THEN 1.0
       WHEN r.customer_match_method IN ('none', 'ambiguous') THEN NULL ELSE round(least(r.auto_score, 1.0), 3) END customer_match_score,
  CASE WHEN r.customer_match_method <> 'name_variant' AND r.sap_sold_to IS NOT NULL AND r.via_partner
       THEN concat(r.via_parvw, ':', r.matched_kunnr) END sold_to_via_partner,
  CASE WHEN r.customer_match_method = 'ambiguous' THEN r.close_sold_tos END candidate_sold_tos,
  CASE WHEN r.customer_match_method = 'ambiguous' THEN r.n_close END n_customer_candidates,
  r.pinned_sold_to, r.pinned_in_sap,
  CASE WHEN r.sap_sold_to IS NULL THEN NULL
       WHEN r.customer_match_method <> 'name_variant' AND r.via_partner AND r.via_parvw = 'WE' THEN r.matched_kunnr
       ELSE coalesce(b.ship_kunnr, CASE WHEN w.n = 1 AND coalesce(trim(r.ship_to), '') = '' THEN w.only_partner END) END sap_ship_to,
  CASE WHEN r.sap_sold_to IS NULL THEN 'no_sold_to'
       WHEN r.customer_match_method <> 'name_variant' AND r.via_partner AND r.via_parvw = 'WE' THEN 'ok'
       WHEN coalesce(trim(r.ship_to), '') = '' THEN 'not_given'
       WHEN b.ship_kunnr IS NULL THEN 'not_found'
       WHEN b.linked THEN 'ok' ELSE 'not_linked' END ship_to_check
FROM res r
LEFT JOIN org g ON g.doc_id = r.doc_id AND g.order_idx = r.order_idx AND g.rn = 1
LEFT JOIN sh_best b ON b.doc_id = r.doc_id AND b.order_idx = r.order_idx
LEFT JOIN n_we w ON w.doc_id = r.doc_id AND w.order_idx = r.order_idx"""


HINT_KEY = 100   # hint rows are resolved as order_idx * HINT_KEY + hint rank (one resolution run for all hints)


def customer_hint_resolution_sql(first, hints, customers, links, sales_orgs, max_token_df=3000):
    """Second customer pass for orders the document did not resolve (customer_match_method = 'none' in `first`).

    first: the customer_resolution_sql result (one row per doc_id, order_idx).
    hints: relation doc_id, order_idx, hint_rank (0..HINT_KEY-1, best first), hint_source, hint, hint_evidence,
           customer_number, ship_to — customer-like texts from the sender / subject / file name (customer_hints.py),
           only for the unresolved orders. The order's printed customer number and ship-to go with every hint, so
           an address on the document still counts as evidence.
    Each hint is resolved exactly like a printed name. Per order the first hint (by rank) that resolves to ONE
    sold-to wins; else the first ambiguous one (its candidates are shown); else the document result stays.
    Same columns as `first` plus customer_source ('document' or the hint source) and customer_hint (evidence)."""
    k = int(HINT_KEY)
    res = customer_resolution_sql(
        f"(SELECT doc_id, order_idx * {k} + hint_rank order_idx, hint customer_name, customer_number, ship_to, "
        f"false customer_is_supplier FROM {hints})",
        customers, links, sales_orgs, max_token_df=max_token_df)
    return f"""
WITH f AS (SELECT * FROM {first}),
hr AS ({res}),
cand AS (
  SELECT hr.*, h.hint_rank, h.hint_source, h.hint_evidence,
    ROW_NUMBER() OVER (PARTITION BY h.doc_id, h.order_idx ORDER BY
      CASE WHEN hr.customer_match_method NOT IN ('none', 'ambiguous') THEN 0 ELSE 1 END, h.hint_rank) pick
  FROM hr JOIN {hints} h ON h.doc_id = hr.doc_id AND h.order_idx * {k} + h.hint_rank = hr.order_idx
  WHERE hr.customer_match_method <> 'none'
),
best AS (
  SELECT c.doc_id, CAST(floor(c.order_idx / {k}) AS INT) order_idx,
         c.* EXCEPT (doc_id, order_idx, hint_rank, hint_source, hint_evidence, pick),
         c.hint_source customer_source, c.hint_evidence customer_hint
  FROM cand c WHERE c.pick = 1
)
SELECT f.*, 'document' customer_source, CAST(NULL AS STRING) customer_hint
FROM f LEFT ANTI JOIN best b ON b.doc_id = f.doc_id AND b.order_idx = f.order_idx
UNION ALL
SELECT * FROM best"""


# ---------------------------------------------------------------------------------------------------------
# material resolution
# ---------------------------------------------------------------------------------------------------------
def material_resolution_sql(lines, materials, sales_orgs, prefix_len=6, sku_overrides=None, with_ean=False):
    """Validate each ordered code against SAP materials listed for the order's sales org.

    lines:     relation with doc_id, order_idx, li_idx, printed_sku, sales_org (the order's SAP sales org; NULL
               when the customer is unresolved -> any configured org counts as listed)
    materials: oi_sap_materials; sku_overrides: optional retailer_sku_map (retailer_sku -> material_no),
               tried before the printed code (the printed code is still used when the pinned one isn't in SAP).
    with_ean:  lines also has printed_ean (the line's barcode, extracted separately): tried after the printed code,
               so a supplier code that isn't in SAP still resolves through the line's EAN.
    Precedence per code: exact (10-char, or 18-digit numeric) -> EAN/UPC (MARA + MARM; 8-14 digits) -> first
    `prefix_len` characters. Exact keeps the full number; a prefix match is valid and resolves to the prefix (SAP
    picks the full number); an EAN resolves when exactly one material listed for the org has it, else it is
    ambiguous (several) — never picked arbitrarily. Quantities are never touched. One row per line.
    """
    n = parse_prefix_len(prefix_len)
    org_arr = f"array({sql_list(sales_orgs)})"
    ov_union = ""
    if sku_overrides:
        ov_union = f"""
  UNION ALL
  SELECT l.doc_id, l.order_idx, l.li_idx, l.sales_org, 1 src_rank, 'retailer_sku' src,
         {code_norm_sql('rs.material_no')} code
  FROM {lines} l
  JOIN (SELECT trim(retailer_sku) retailer_sku, min(material_no) material_no FROM {sku_overrides}
        WHERE coalesce(trim(material_no), '') <> '' GROUP BY trim(retailer_sku)) rs
    ON rs.retailer_sku = trim(l.printed_sku)"""
    ean_union = ""
    if with_ean:
        ean_union = f"""
  UNION ALL
  SELECT doc_id, order_idx, li_idx, sales_org, 3 src_rank, 'document_ean' src, {code_norm_sql('printed_ean')} code
  FROM {lines} WHERE printed_ean IS NOT NULL"""
    return f"""
WITH c AS (
  SELECT doc_id, order_idx, li_idx, sales_org, 2 src_rank, 'document' src, {code_norm_sql('printed_sku')} code
  FROM {lines}{ov_union}{ean_union}
),
c2 AS (
  SELECT *,
    code RLIKE '^[0-9]{{8,14}}$' looks_ean,
    {ean_key_sql('code')} ean_key,
    CASE WHEN length(code) >= {n} AND code NOT RLIKE '^[0-9]{{12,14}}$' THEN substr(code, 1, {n}) END prefix_key,
    CASE WHEN code RLIKE '^[0-9]{{1,17}}$' THEN lpad(code, 18, '0') END code18
  FROM c WHERE code <> ''
),
m AS (
  SELECT matnr, prefix, eans, sales_orgs, deleted, coalesce(text_de, text_en) text FROM {materials}
),
hits AS (
  SELECT c2.doc_id, c2.order_idx, c2.li_idx, c2.src_rank, c2.src, c2.code, 1 kind_rank, 'exact' kind, m.matnr,
    m.text, m.deleted, (c2.sales_org IS NULL OR array_contains(m.sales_orgs, c2.sales_org)) listed
  FROM c2 JOIN m ON m.matnr = c2.code
  UNION ALL
  SELECT c2.doc_id, c2.order_idx, c2.li_idx, c2.src_rank, c2.src, c2.code, 1, 'exact', m.matnr, m.text, m.deleted,
    (c2.sales_org IS NULL OR array_contains(m.sales_orgs, c2.sales_org))
  FROM c2 JOIN m ON m.matnr = c2.code18 AND c2.code18 <> c2.code
  UNION ALL
  SELECT c2.doc_id, c2.order_idx, c2.li_idx, c2.src_rank, c2.src, c2.code, 2, 'ean', e.matnr, e.text, e.deleted,
    (c2.sales_org IS NULL OR array_contains(e.sales_orgs, c2.sales_org))
  FROM c2 JOIN (SELECT m.*, ean FROM m LATERAL VIEW explode(eans) t AS ean) e ON e.ean = c2.ean_key
  WHERE c2.looks_ean
  UNION ALL
  SELECT c2.doc_id, c2.order_idx, c2.li_idx, c2.src_rank, c2.src, c2.code, 3, 'prefix', m.matnr, m.text, m.deleted,
    (c2.sales_org IS NULL OR array_contains(m.sales_orgs, c2.sales_org))
  FROM c2 JOIN m ON m.prefix = c2.prefix_key
),
k AS (   -- per line + code source + match kind
  SELECT doc_id, order_idx, li_idx, src_rank, src, code, kind_rank, kind,
    count(DISTINCT matnr) n_all,
    count(DISTINCT CASE WHEN listed THEN matnr END) n_listed,
    min(CASE WHEN listed THEN matnr END) one_matnr,
    min_by(text, CASE WHEN listed THEN 0 ELSE 1 END) text,
    bool_and(deleted) all_deleted
  FROM hits GROUP BY ALL
),
d AS (
  SELECT k.*,
    CASE WHEN n_listed = 0 THEN 'not_listed'
         WHEN kind = 'ean' AND n_listed > 1 THEN 'ean_ambiguous' END issue,
    CASE WHEN n_listed = 0 THEN NULL
         WHEN kind = 'exact' THEN one_matnr
         WHEN kind = 'ean' AND n_listed = 1 THEN one_matnr
         WHEN kind = 'prefix' THEN substr(code, 1, {n}) END resolved
  FROM k
),
best AS (   -- resolved beats unresolved; then pinned (retailer_sku) before document code; exact > EAN > prefix
  SELECT * FROM (
    SELECT d.*, ROW_NUMBER() OVER (PARTITION BY doc_id, order_idx, li_idx
      ORDER BY CASE WHEN resolved IS NOT NULL THEN 0 ELSE 1 END, src_rank, kind_rank,
               CASE WHEN issue = 'ean_ambiguous' THEN 0 ELSE 1 END) rn
    FROM d) WHERE rn = 1
)
SELECT l.doc_id, l.order_idx, l.li_idx,
  CASE WHEN b.resolved IS NOT NULL THEN b.kind ELSE 'none' END sku_resolve_method,
  coalesce(b.src = 'retailer_sku', false) sku_from_retailer_map,
  b.resolved resolved_material_no,
  b.resolved IS NOT NULL sku_resolved,
  CASE WHEN b.kind = 'ean' AND b.issue = 'ean_ambiguous' THEN b.n_listed
       WHEN b.resolved IS NOT NULL THEN b.n_listed END material_candidates,
  coalesce(b.issue, CASE WHEN b.doc_id IS NULL THEN 'not_found' END) material_issue,
  b.text sap_material_text,
  coalesce(b.resolved IS NOT NULL AND b.all_deleted, false) sap_material_deleted,
  coalesce(l.sales_org, array_join({org_arr}, ', ')) material_sales_org
FROM {lines} l
LEFT JOIN best b ON b.doc_id = l.doc_id AND b.order_idx = l.order_idx AND b.li_idx = l.li_idx"""


def region_join_sql(alias, sales_org_col, country_col, regions_table, region_map_table):
    """LEFT JOINs giving `<alias>_region` columns for an order in sap mode. Region = the business's region_map
    (country -> region) if it lists the sold-to's country, else the SAP affiliate of (sales org, country), else
    the sales org's most common affiliate, else 'Other'; 'Unassigned' without a resolved sold-to."""
    joins = f"""
LEFT JOIN (SELECT upper(country) country, any_value(region) region FROM {region_map_table} GROUP BY 1) {alias}_rm
  ON {alias}_rm.country = upper({country_col})
LEFT JOIN {regions_table} {alias}_g ON {alias}_g.sales_org = {sales_org_col} AND {alias}_g.country = {country_col}
LEFT JOIN (SELECT sales_org, max_by(affiliate, struct(n, affiliate)) affiliate
           FROM (SELECT sales_org, affiliate, count(*) n FROM {regions_table} GROUP BY sales_org, affiliate)
           GROUP BY sales_org) {alias}_go
  ON {alias}_go.sales_org = {sales_org_col}"""
    expr = (f"CASE WHEN {sales_org_col} IS NULL THEN 'Unassigned' "
            f"ELSE coalesce({alias}_rm.region, {alias}_g.affiliate, {alias}_go.affiliate, 'Other') END")
    return joins, expr
