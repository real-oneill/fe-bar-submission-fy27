"""Customer hints from the sender / subject / file name (src/lib/customer_hints.py) — pure Python."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))
import customer_hints as ch  # noqa: E402

_BRANDS = {"solenne paris", "atelier noor", "lune rouge", "ember oak", "velour cosmetics", "mistral hair", "kori botanicals"}


def is_supplier(name):
    n = " ".join(re.sub(r"[^a-z0-9 ]", " ", str(name).lower()).split())
    return bool(re.search(r"maison\s*solenne|maisonsolenne", n)) or n in _BRANDS


def test_parse_sender():
    assert ch.parse_sender('"Jan Jansen" <Jan@Shop.NL>') == ("Jan Jansen", "jan@shop.nl")
    assert ch.parse_sender("orders@parfuemerie-brandt.de") == (None, "orders@parfuemerie-brandt.de")
    assert ch.parse_sender("Brandt Bestellungen") == ("Brandt Bestellungen", None)
    assert ch.parse_sender(None) == (None, None)


def test_mail_header():
    body = "From: Moma Beauty <inkoop@momabeauty.nl>\nSubject: Bestelling door Moma Beauty B.V.\n\nHallo"
    assert ch.mail_header(body, "From") == "Moma Beauty <inkoop@momabeauty.nl>"
    assert ch.mail_header(body, "Subject") == "Bestelling door Moma Beauty B.V."
    assert ch.mail_header("no headers here", "From") is None


def test_domain_hint():
    assert ch.domain_hint("orders@mueller-drogerie.de") == "mueller drogerie"
    assert ch.domain_hint("inkoop@momabeauty.nl") == "momabeauty"
    assert ch.domain_hint("buyer@orders.shop.co.uk") == "shop"
    assert ch.domain_hint("cs@maisonsolenne.example") is None     # supplier
    assert ch.domain_hint("x@eu.maisonsolenne.example") is None  # supplier
    assert ch.domain_hint("jan.jansen@gmail.com") is None          # free mail: one domain, many customers
    assert ch.domain_hint("salon@t-online.de") is None
    assert ch.domain_hint("not an address") is None


def test_clean_words():
    assert ch.clean_words("Bestelling Bergen  5375217043.msg") == ["bergen"]
    assert ch.clean_words("BESTELLUNG BES 26930.pdf") == ["bes"]
    assert ch.clean_words("Bestellung vom 18.09.2026.pdf") == []
    assert ch.clean_words("CL Bestellung Schleien 17.09.2026.xlsx", is_supplier) == ["schleien"]
    assert ch.clean_words("Bon de commande ATELIER NOOR 20260915 FRET200002477.xlsx", is_supplier) == []
    assert ch.clean_words("Bestellformular LUNE ROUGE_ab Juli 2026_FY27 H1_PB30 C100_Wholesale.xlsx",
                          is_supplier) == []
    assert ch.clean_words("CDE MAISON SOLENNE 24_09_26.xlsx", is_supplier) == []
    # markets and trials are not customers (a subject "Test" must not match a customer named Test)
    assert ch.clean_words("15.06.26 VP FRANCE Tarifs Juin 2026 Velour Cosmetics - Full Assortiment - DEF.xlsx", is_supplier) == []
    assert ch.clean_words("Test") == []


def test_customer_hints_order_and_sources():
    h = ch.customer_hints(senders=["Moma Beauty <inkoop@momabeauty.nl>"], subjects=["Bestelling door Moma Beauty B.V."],
                          file_name="Bestelling door Moma Beauty B_V_  5375366565.msg / Inkooporder 041455.pdf",
                          is_supplier=is_supplier)
    assert h == [("sender_domain", "momabeauty", "inkoop@momabeauty.nl"),
                 ("sender_name", "moma beauty", "Moma Beauty")]                 # same hint from subject/file: once


def test_customer_hints_customer_inside_forwarded_mail():
    # the .msg's own From: (the retailer) first, the internal mailbox sender adds nothing
    h = ch.customer_hints(senders=["inkoop@drogisterij-bergen.nl", "cs.benelux@maisonsolenne.example"],
                          subjects=["FW: Bestelling"], file_name="Bestelling Bergen 5375217043.msg / body.txt",
                          is_supplier=is_supplier)
    assert h == [("sender_domain", "drogisterij bergen", "inkoop@drogisterij-bergen.nl"),
                 ("file_name", "bergen", "Bestelling Bergen 5375217043.msg / body.txt")]


def test_customer_hints_supplier_sender_and_brand_file():
    h = ch.customer_hints(senders=["rep@maisonsolenne.example"], subjects=["Test"],
                          file_name="Launch recap source details_v2_0.xlsx", is_supplier=is_supplier)
    assert all(s != "sender_domain" for s, _, _ in h)
    assert ch.customer_hints(file_name="Bon de commande ATELIER NOOR 20260915 FRET200002476.xlsx",
                             is_supplier=is_supplier) == []
    assert ch.customer_hints(senders=["jan.jansen@gmail.com"]) == []                  # free mail, no name
