"""Customer hints from the email and file around an order, for orders whose document names no customer that SAP
knows (master_source=sap).

Each hint is a short customer-like text that Gold resolves against the SAP customer master with the same
customer_resolution_sql as the printed customer name. Hints, best first:

  sender_domain  the sender's email domain: orders@mueller-drogerie.de -> "mueller drogerie"
  sender_name    the sender's display name: "Parfümerie Brandt Bestellungen" -> "brandt"
  subject        the email subject, order words removed: "Bestelling door Moma Beauty B.V." -> "moma beauty b v"
  file_name      the attachment / email file name, same cleaning: "Bestelling Bergen 5375217043.msg" -> "bergen"

Never a hint: the supplier's own domains and brands (the supplier sends and is named on its own orders), free-mail domains (one
domain, many customers), dates, numbers and words that only say "this is an order".
"""
import re
import unicodedata

HINT_LABELS = {
    "sender_domain": "sender's email domain",
    "sender_name": "sender's name",
    "subject": "email subject",
    "file_name": "file name",
}
HINT_RANK = {s: i for i, s in enumerate(HINT_LABELS)}

# the supplier's own mail (internal senders forward orders; the CS team writes subjects) is never the customer.
INTERNAL_DOMAIN_RE = re.compile(r"(?i)\.(maisonsolenne|solenne)\.")
FREE_MAIL_DOMAINS = {
    "gmail", "googlemail", "hotmail", "outlook", "live", "msn", "yahoo", "ymail", "icloud", "me", "mac", "aol",
    "gmx", "web", "t-online", "freenet", "arcor", "posteo", "mail", "email", "orange", "wanadoo", "free", "sfr",
    "laposte", "bbox", "neuf", "club-internet", "bluewin", "sunrise", "hispeed", "aon", "chello", "a1", "ziggo",
    "kpnmail", "planet", "home", "hetnet", "xs4all", "casema", "telenet", "skynet", "proximus", "libero", "virgilio",
    "tiscali", "alice", "btinternet", "sky", "virginmedia", "talktalk", "protonmail", "proton", "zoho", "yandex",
    "seznam", "wp", "o2", "onet", "interia",
}
# second-level public suffixes: the registrable name is one label further left (shop.co.uk -> "shop")
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "or", "ne"}
# subdomains that say nothing about the company: orders.mueller.de -> "mueller"
_GENERIC_SUBDOMAINS = {"mail", "mx", "smtp", "email", "orders", "order", "bestellung", "purchasing", "einkauf", "edi",
                       "noreply", "no-reply", "info", "www", "eu", "de", "at", "ch", "fr", "nl", "be", "uk"}

# Words that say "this is an order / an email / a file", in the EMEA order languages. Dropped from subjects and
# file names before matching, as are months, dates, numbers and words shorter than 3 characters.
ORDER_WORDS = {
    # en
    "order", "orders", "ordering", "new", "purchase", "po", "replenishment", "reorder", "request", "form", "copy",
    "confirmation", "attached", "attachment", "please", "thanks", "thank", "per", "from", "for", "via", "with",
    "subject", "email", "mail", "excel", "file", "scan", "scanned", "fax", "print", "printed", "document", "doc",
    "deal", "promo", "promotion", "pricing", "price", "prices", "pricelist", "wholesale", "list", "sheet", "target",
    "draft", "final", "def", "update", "updated", "version",
    # de / at / ch
    "bestellung", "bestellungen", "bestellformular", "bestellnr", "bestellnummer", "einkaufsbestellung", "auftrag",
    "nachbestellung", "lieferung", "vom", "fuer", "und", "mit", "bitte", "anbei", "angebot", "angebote",
    "preisanpassung", "preisliste", "druckversion", "herbst", "fruehling", "sommer", "winter", "nummer",
    # nl / be
    "bestelling", "bestellen", "bestelformulier", "inkooporder", "inkoopopdracht", "door", "voor", "van", "svp",
    "promotie", "nieuwe", "nieuw",
    # fr
    "commande", "commandes", "cde", "cdes", "bdc", "bon", "achat", "reassort", "reassortiment", "tarifs", "tarif",
    "assortiment", "full", "collat", "fin", "annee", "pour", "les", "des", "une", "par", "avec",
    # es / it
    "pedido", "pedidos", "orden", "compra", "ordine", "ordini", "acquisto",
    # mail prefixes and file types
    "re", "fw", "fwd", "aw", "wg", "tr", "rv", "sv", "vs", "antw", "doorst",
    "xlsx", "xlsm", "xls", "csv", "pdf", "txt", "msg", "eml", "docx", "body", "no",
}
# Countries / regions / test words name a market or a trial, not a customer ("VP FRANCE Tarifs", subject "Test")
_PLACE_TEST_WORDS = {
    "france", "germany", "deutschland", "austria", "oesterreich", "osterreich", "schweiz", "suisse", "switzerland",
    "belgium", "belgique", "belgie", "nederland", "netherlands", "holland", "luxembourg", "spain", "espana", "italy",
    "italia", "portugal", "england", "britain", "ireland", "europe", "emea", "dach", "benelux", "fbnl", "bnl",
    "nordics", "international", "export", "test", "testing", "sample", "samples", "example", "examples", "demo",
}
# the supplier's own name ("Maison Solenne Bestellung") — the supplier, never the customer
_SUPPLIER_WORDS = {"maison", "solenne", "maisonsolenne"}
_MONTH_WORDS = {
    "jan", "januar", "january", "janvier", "januari", "feb", "februar", "february", "fevrier", "februari", "mar",
    "maerz", "march", "mars", "maart", "apr", "april", "avril", "mai", "may", "mei", "jun", "juni", "june", "juin",
    "jul", "juli", "july", "juillet", "aug", "august", "aout", "augustus", "sep", "sept", "september", "septembre",
    "okt", "oct", "oktober", "october", "octobre", "nov", "november", "novembre", "dez", "dec", "dezember",
    "december", "decembre",
}
_EXT_RE = re.compile(r"(?i)\.(xlsx|xlsm|xls|csv|pdf|txt|msg|eml|docx?|png|jpe?g|tiff?)$")
_EMAIL_RE = re.compile(r"[\w.+'-]+@([\w-]+(?:\.[\w-]+)+)")


def _ascii(s):
    t = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def parse_sender(value):
    """'Jan Jansen <jan@shop.nl>' / 'jan@shop.nl' / 'Jan Jansen' -> (display name or None, email or None)."""
    v = str(value or "").strip()
    if not v:
        return None, None
    m = _EMAIL_RE.search(v)
    email = m.group(0).lower() if m else None
    name = re.sub(r"<[^>]*>", " ", v)
    if email:
        name = name.replace(m.group(0), " ")
    name = " ".join(name.replace('"', " ").replace("'", " ").split()).strip(" ,;")
    return (name or None), email


def mail_header(text, header):
    """First 'From:' / 'Subject:' line at the top of an unpacked email body part (Silver writes them there)."""
    for line in str(text or "").splitlines()[:6]:
        if line.lower().startswith(header.lower() + ":"):
            return line.split(":", 1)[1].strip() or None
    return None


def domain_hint(email):
    """orders@mueller-drogerie.de -> 'mueller drogerie'; supplier, free-mail and unparsable addresses -> None."""
    m = _EMAIL_RE.search(str(email or ""))
    if not m:
        return None
    domain = m.group(1).lower()
    if INTERNAL_DOMAIN_RE.search("." + domain + "."):
        return None
    labels = domain.split(".")
    if len(labels) < 2:
        return None
    i = len(labels) - 2
    if i >= 1 and labels[i] in _SECOND_LEVEL:
        i -= 1
    name = labels[i]
    if name in FREE_MAIL_DOMAINS or name in _GENERIC_SUBDOMAINS:
        return None
    words = clean_words(name.replace("-", " "))
    return " ".join(words) or None


def clean_words(text, is_supplier=None):
    """Customer-name-like words of a subject / file name / display name: order words, months, dates, numbers,
    Supplier brands and words < 3 characters dropped. 'BESTELLUNG Bergen 22.09.2026 (1).xlsx' -> ['bergen']."""
    t = _EXT_RE.sub("", str(text or "").strip())
    t = re.sub(r"[_]+", " ", t)
    words = [w for w in re.split(r"[^a-z0-9]+", _ascii(t)) if w]
    out = []
    for w in words:
        if len(w) < 3 or w in ORDER_WORDS or w in _MONTH_WORDS or w in _SUPPLIER_WORDS or w in _PLACE_TEST_WORDS or re.search(r"\d", w):
            continue
        if is_supplier is not None and is_supplier(w):
            continue
        out.append(w)
    # multi-word supplier brands ("lune rouge", "atelier noor", "ember oak") are dropped as a whole
    if is_supplier is not None:
        joined = " ".join(out)
        for n in (3, 2):
            for i in range(len(out) - n + 1):
                phrase = " ".join(out[i:i + n])
                if is_supplier(phrase):
                    joined = re.sub(rf"(^| ){re.escape(phrase)}( |$)", " ", joined)
        out = joined.split()
    return out


def customer_hints(senders=(), subjects=(), file_name=None, is_supplier=None):
    """[(source, hint, evidence)] best first, distinct hints, each 3..60 characters.

    senders:   raw sender values, best first: the From: of an unpacked email (the customer's own mail inside a
               forwarded .msg) before the mailbox sender. 'Name <a@b.c>', 'a@b.c' or a display name.
    subjects:  email subjects, best first.
    file_name: the attachment / part name. An unpacked part ('Bestelling 5374449405.msg / order.pdf') uses every
               path element: the email's own name names the customer more often than its attachment.
    is_supplier(text): Gold's supplier entity/brand test; supplier names are never hints.
    evidence is the raw value the hint came from (the address, display name, subject or file name), for the
    review reason."""
    found, seen = [], set()

    def add(source, hint, evidence):
        h = " ".join(str(hint or "").split())
        if 3 <= len(h) <= 60 and h not in seen and not (is_supplier and is_supplier(h)):
            seen.add(h)
            found.append((HINT_RANK[source], len(found), source, h, str(evidence)))

    for raw in senders or ():
        name, email = parse_sender(raw)
        if email:
            add("sender_domain", domain_hint(email), email)
        if name:
            add("sender_name", " ".join(clean_words(name, is_supplier)), name)
    for subj in subjects or ():
        add("subject", " ".join(clean_words(subj, is_supplier)), subj)
    parts = [p for p in re.split(r"\s+/\s+", str(file_name or "")) if p and p.lower() != "body.txt"]
    add("file_name", " ".join(w for p in parts for w in clean_words(p, is_supplier)), file_name)
    return [(src, h, ev) for _, _, src, h, ev in sorted(found)]
