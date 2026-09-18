import os
import re
import html
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urlencode


# ============================================================
# CONFIG
# ============================================================

SHOPIFY_STORE = "it3u3i-5e.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]

API_VERSION = "2026-01"

OUTPUT_FILE = "kelkoo.xml"

SHOP_DOMAIN = "https://saivera.net"
FRENCH_PATH = "/fr/products/"

TIMEOUT = 60


# ============================================================
# SHOPIFY GRAPHQL
# ============================================================

QUERY = """
query GetProducts($cursor: String) {

  products(
    first: 100
    after: $cursor
    query: "status:ACTIVE"
  ) {

    pageInfo {
      hasNextPage
      endCursor
    }

    nodes {

      id
      title
      handle
      vendor
      descriptionHtml

      category {
        name
        fullName
      }

      frenchTranslations: translations(locale: "fr") {
        key
        value
      }

      images(first: 1) {
        nodes {
          url
        }
      }

      variants(first: 1) {
        nodes {
          sku
          price
          availableForSale
        }
      }
    }
  }
}
"""


# ============================================================
# HELPERS
# ============================================================

def shopify_request(query, variables):
    url = (
        f"https://{SHOPIFY_STORE}/admin/api/"
        f"{API_VERSION}/graphql.json"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    }

    response = requests.post(
        url,
        headers=headers,
        json={
            "query": query,
            "variables": variables,
        },
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        print("GRAPHQL ERRORS")
        print("=" * 80)
        print(data["errors"])
        raise RuntimeError("Shopify GraphQL request failed")

    return data["data"]


def clean_html(text):
    if not text:
        return ""

    text = html.unescape(text)

    # Remove scripts/styles
    text = re.sub(
        r"<(script|style).*?>.*?</\1>",
        " ",
        text,
        flags=re.I | re.S,
    )

    # Replace common block tags with spaces
    text = re.sub(
        r"</?(p|div|br|li|ul|ol|h[1-6])[^>]*>",
        " ",
        text,
        flags=re.I,
    )

    # Remove remaining HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def truncate(text, max_length):
    if not text:
        return ""

    text = text.strip()

    if len(text) <= max_length:
        return text

    return text[:max_length - 3].rstrip() + "..."


def xml_text(parent, tag, value):
    if value is None:
        value = ""

    element = ET.SubElement(parent, tag)
    element.text = str(value)
    return element


def translation_map(translations):
    result = {}

    for item in translations or []:
        key = item.get("key")
        value = item.get("value")

        if key and value:
            result[key] = value

    return result


# ============================================================
# BRAND
# ============================================================

BRAND_RULES = [
    ("microsoft", "Microsoft"),
    ("windows", "Microsoft"),
    ("office", "Microsoft"),
    ("outlook", "Microsoft"),
    ("word", "Microsoft"),
    ("excel", "Microsoft"),
    ("powerpoint", "Microsoft"),
    ("visio", "Microsoft"),
    ("project", "Microsoft"),
    ("xbox", "Microsoft"),
    ("minecraft", "Microsoft"),

    ("kaspersky", "Kaspersky"),
    ("norton", "Norton"),
    ("mcafee", "McAfee"),
    ("avast", "Avast"),
    ("bitdefender", "Bitdefender"),
    ("eset", "ESET"),

    ("surfshark", "Surfshark"),
    ("nordvpn", "NordVPN"),

    ("adobe", "Adobe"),
    ("autodesk", "Autodesk"),
    ("google", "Google"),

    ("ea ", "EA"),
    ("electronic arts", "EA"),
    ("capcom", "Capcom"),
    ("koei tecmo", "Koei Tecmo"),
    ("pearl abyss", "Pearl Abyss"),
    ("embark studios", "Embark Studios"),
    ("io interactive", "IO Interactive"),
]


def detect_brand(product):
    title = product.get("title", "")
    vendor = product.get("vendor", "")

    text = f"{title} {vendor}".lower()

    for keyword, brand in BRAND_RULES:
        if keyword in text:
            return brand

    # Shopify vendor if available
    if vendor and vendor.strip():
        return vendor.strip()[:70]

    # SAIVERA may be used only when the product is generic
    return "SAIVERA"


# ============================================================
# CATEGORY
# ============================================================

def detect_category(product, brand):
    title = product.get("title", "").lower()
    vendor = product.get("vendor", "").lower()

    text = f"{title} {vendor}"

    # Xbox / gaming subscriptions
    if text.startswith("xbox") or "xbox" in text:
        return "Jeux vidéo > Abonnements gaming"

    if (
        "game pass" in text
        or "gaming subscription" in text
        or "playstation plus" in text
        or "ps plus" in text
    ):
        return "Jeux vidéo > Abonnements gaming"

    # Antivirus / VPN
    if any(
        x in text
        for x in [
            "kaspersky",
            "norton",
            "mcafee",
            "avast",
            "bitdefender",
            "eset",
            "antivirus",
        ]
    ):
        return "Logiciels > Sécurité > Antivirus"

    if any(
        x in text
        for x in [
            "surfshark",
            "nordvpn",
            "vpn",
        ]
    ):
        return "Logiciels > Sécurité > VPN"

    # Microsoft Windows
    if "windows" in text:
        return "Logiciels > Systèmes d'exploitation > Windows"

    # Microsoft Office
    if any(
        x in text
        for x in [
            "office",
            "outlook",
            "word",
            "excel",
            "powerpoint",
            "access",
            "publisher",
            "visio",
            "project",
        ]
    ):
        return "Logiciels > Bureautique > Microsoft Office"

    # Adobe
    if "adobe" in text:
        return "Logiciels > Création graphique > Adobe"

    # Autodesk / CAD
    if any(
        x in text
        for x in [
            "autocad",
            "autodesk",
            "3ds max",
            "maya",
            "revit",
            "civil 3d",
        ]
    ):
        return "Logiciels > CAO et conception"

    # Games
    if any(
        x in text
        for x in [
            "game",
            "jeu vidéo",
            "gaming",
            "minecraft",
        ]
    ):
        return "Jeux vidéo > Jeux vidéo numériques"

    # PDF / utilities
    if any(
        x in text
        for x in [
            "pdf",
            "acrobat",
            "utilities",
            "utility",
        ]
    ):
        return "Logiciels > Utilitaires"

    # Generic software
    if brand and brand != "SAIVERA":
        return "Logiciels > Logiciels numériques"

    return "Logiciels > Logiciels numériques"


# ============================================================
# FETCH PRODUCTS
# ============================================================

def get_all_products():
    products = []
    cursor = None
    page = 1

    while True:
        print(f"Downloading Shopify products page {page}...")

        data = shopify_request(
            QUERY,
            {
                "cursor": cursor,
            },
        )

        connection = data["products"]

        nodes = connection.get("nodes", [])

        print(f"Products received: {len(nodes)}")

        products.extend(nodes)

        if not connection["pageInfo"]["hasNextPage"]:
            break

        cursor = connection["pageInfo"]["endCursor"]
        page += 1

    print(f"Total Shopify products: {len(products)}")

    return products


# ============================================================
# FRENCH DATA
# ============================================================

def get_french_data(product):
    translations = translation_map(
        product.get("frenchTranslations", [])
    )

    french_title = translations.get("title")
    french_description = translations.get("body_html")

    # Some Shopify translations may use different body key
    if not french_description:
        french_description = translations.get("description")

    # Fallback to original Shopify data if French translation
    # does not exist.
    if not french_title:
        french_title = product.get("title", "")

    if not french_description:
        french_description = product.get(
            "descriptionHtml",
            ""
        )

    return (
        clean_html(french_title),
        clean_html(french_description),
    )


# ============================================================
# BUILD PRODUCT
# ============================================================

def build_product(product):

    variants = product.get("variants", {}).get("nodes", [])

    if not variants:
        print(
            f"SKIP: no variant -> {product.get('title')}"
        )
        return None

    variant = variants[0]

    sku = (variant.get("sku") or "").strip()

    # Kelkoo id must be unique and max 50 chars.
    product_id = sku

    if not product_id:
        product_id = product.get("id", "").split("/")[-1]

    product_id = product_id[:50]

    french_title, french_description = get_french_data(
        product
    )

    french_title = truncate(
        french_title,
        150,
    )

    french_description = truncate(
        french_description,
        3000,
    )

    if not french_title:
        print(
            f"SKIP: no title -> {product.get('title')}"
        )
        return None

    price = variant.get("price")

    if price is None:
        print(
            f"SKIP: no price -> {product.get('title')}"
        )
        return None

    try:
        price = f"{float(price):.2f}"
    except Exception:
        print(
            f"SKIP: invalid price -> {product.get('title')}"
        )
        return None

    image_nodes = (
        product.get("images", {})
        .get("nodes", [])
    )

    if not image_nodes:
        print(
            f"SKIP: no image -> {product.get('title')}"
        )
        return None

    image_url = image_nodes[0].get("url")

    if not image_url:
        print(
            f"SKIP: empty image -> {product.get('title')}"
        )
        return None

    handle = product.get("handle")

    if not handle:
        print(
            f"SKIP: no handle -> {product.get('title')}"
        )
        return None

    landing_page_url = (
        f"{SHOP_DOMAIN}"
        f"{FRENCH_PATH}"
        f"{handle}"
    )

    tracking_params = urlencode(
        {
            "utm_source": "kelkoofr",
            "utm_medium": "cpc",
            "utm_campaign": "kelkooclick",
            "utm_source_platform": "KelkooGroup",
        }
    )

    product_url = (
        f"{landing_page_url}?{tracking_params}"
    )

    brand = detect_brand(product)

    merchant_category = detect_category(
        product,
        brand,
    )

    # Kelkoo availability:
    # 1 = In stock
    # 6 = Not in stock
    availability = (
        "1"
        if variant.get("availableForSale")
        else "6"
    )

    return {
        "id": product_id,
        "title": french_title,
        "description": french_description,
        "product-url": product_url,
        "landing-page-url": landing_page_url,
        "image-url": image_url,
        "price": price,
        "availability": availability,
        "brand": brand,
        "merchant-category": merchant_category,
        "delivery-cost": "0",
        "delivery-time": "Instant",
        "condition": "9",
    }


# ============================================================
# XML
# ============================================================

def build_xml(products):

    root = ET.Element("products")

    for product in products:

        item = ET.SubElement(
            root,
            "product",
        )

        xml_text(item, "id", product["id"])
        xml_text(item, "title", product["title"])

        xml_text(
            item,
            "product-url",
            product["product-url"],
        )

        xml_text(
            item,
            "landing-page-url",
            product["landing-page-url"],
        )

        xml_text(
            item,
            "price",
            product["price"],
        )

        xml_text(
            item,
            "brand",
            product["brand"],
        )

        xml_text(
            item,
            "description",
            product["description"],
        )

        xml_text(
            item,
            "image-url",
            product["image-url"],
        )

        xml_text(
            item,
            "merchant-category",
            product["merchant-category"],
        )

        xml_text(
            item,
            "availability",
            product["availability"],
        )

        xml_text(
            item,
            "delivery-cost",
            product["delivery-cost"],
        )

        xml_text(
            item,
            "delivery-time",
            product["delivery-time"],
        )

        xml_text(
            item,
            "condition",
            product["condition"],
        )

    rough_xml = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )

    parsed = minidom.parseString(rough_xml)

    pretty_xml = parsed.toprettyxml(
        indent="  ",
        encoding="UTF-8",
    )

    # Remove blank lines created by minidom
    pretty_xml = b"\n".join(
        line
        for line in pretty_xml.splitlines()
        if line.strip()
    )

    return pretty_xml


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("SAIVERA - KELKOO FRANCE FEED")
    print("=" * 80)

    products = get_all_products()

    print("=" * 80)
    print("Building French Kelkoo products...")
    print("=" * 80)

    feed_products = []

    for product in products:

        result = build_product(product)

        if result:
            feed_products.append(result)

            print(
                f"OK: {result['title']} "
                f"| {result['price']} EUR "
                f"| {result['brand']} "
                f"| stock={result['availability']}"
            )

    print("=" * 80)
    print(
        f"Products included in feed: "
        f"{len(feed_products)}"
    )
    print("=" * 80)

    if not feed_products:
        raise RuntimeError(
            "No products were generated. "
            "The feed was NOT created."
        )

    xml_data = build_xml(feed_products)

    with open(
        OUTPUT_FILE,
        "wb",
    ) as f:
        f.write(xml_data)

    print(
        f"Feed created successfully: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Feed URL after GitHub Pages deployment: "
        f"https://feed.saivera.net/{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
