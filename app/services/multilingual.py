"""Multilingual classification and validated drafting (English, Hindi, Hinglish).

A structured message object is built from server facts first; prose is
rendered from it afterwards. Validation runs before wording generation, after
wording generation, and again at exact-version approval. Amounts, dates,
negation, and disputed-versus-undisputed meaning are server-owned and must
survive byte-identical in every language.
"""
from datetime import date
from decimal import Decimal
import re

from app.services.negotiation import guard_outbound
from app.services.security import detect_prompt_injection, normalize_untrusted

LANGUAGES = ("en", "hi", "hinglish")

# Markers are ELECTIVE Hindi: grammar plus content words with an easy English
# equivalent, whose use signals Hinglish comfort. Necessary vocabulary is
# deliberately excluded: goods names (masala, atta, dal), packaging/quantity
# terms in list context (bora, peti, khep), address tokens (nagar, gali,
# mohalla, chowk, sadak, marg, basti, tehsil, zila, uttar), Indian-English
# business terms (lakh, crore, mandi, bazaar, godown), and English collisions
# (the, me, to, so, do, din, door, band, par, ya, de, lat, peer, tel, gram,
# path, chain, data, rate, lot, tab, date). Names are excluded too (Jo excepted
# below): malik, babu, afsar, aman, shanti, vivek, vidya, anand, seth, han,
# hal, sahara, lakshya, kar is a documented tradeoff (Bengali surname Kar can
# flip an English sentence; bounded because drafts need staff approval).
HINGLISH_MARKERS = (
    # Core grammar: postpositions, pronouns, auxiliaries, verbs.
    "se", "ko", "ka", "ki", "ke", "ne", "mein", "mai", "hum", "tum", "aap",
    "ye", "yeh", "wo", "woh", "jo", "kar", "lo", "hai", "karna", "dena",
    "milna", "aana", "jaana", "hona", "hota", "hote", "hoti", "hoga", "hogi",
    "honge", "hua", "hui", "huye", "tha", "thi", "hu", "raha", "rahi", "rahe",
    "dunga", "dungi", "doge", "karunga", "karungi", "karoge", "lenge",
    "chahiye", "chahte", "sakta", "sakte", "sakti", "padega", "padegi",
    "aaya", "aaye", "aayi", "aayega", "aayegi", "gaya", "gaye", "gayi",
    "liya", "liye", "diya", "diye", "kiya", "kiye", "dijiye", "karke",
    "wala", "wale", "wali", "hamein", "humein", "mujhe", "tumhe", "tumhein",
    "aapko", "mera", "meri", "mere", "hamara", "hamare", "hamari", "aapka",
    "aapke", "aapki", "iske", "uske", "karenge", "denge", "bhej",
    # Questions, conjunctions, discourse.
    "kaun", "kya", "kyaa", "kaunsa", "kaunsi", "kaisa", "kaisi", "kaise",
    "kyon", "kyun", "kab", "kitna", "kitni", "kitne", "kahan", "kahaan",
    "kidhar", "jaisa", "jaise", "waisa", "waise", "aisa", "aise", "kabhi",
    "aur", "lekin", "magar", "agar", "toh", "phir", "warna", "varna",
    "kyunki", "isliye", "taaki", "jab", "bhi", "sirf", "alawa", "bina",
    "sahit", "samet", "shamil", "shaamil", "kharij", "alag", "tak",
    "badle", "evaz", "badla", "tarah", "tareeka", "dhang", "nahi", "nahin",
    # Time.
    "aaj", "kal", "abhi", "roz", "subah", "shaam", "raat", "der", "deri",
    "jaldi", "turant", "saal", "mahina", "mahine", "hafta", "hafte",
    "tarikh", "hamesha", "aksar", "agle", "pichle", "pehla", "pehli",
    "dusra", "doosra", "teesra", "aakhri", "aakhir", "shuru", "shuruaat",
    "samay", "mohlat",
    # Quantity.
    "sau", "hazaar", "darjan", "kul", "poora", "poori", "pura", "puri",
    "aadha", "aadhi", "kuch", "kuchh", "koi", "sab", "sabhi", "har",
    "itna", "itni", "itne", "utna", "utni", "jitna", "jitni", "bahut",
    "bohot", "bohat", "bahot", "kaafi", "thoda", "thora", "thode",
    "zyada", "jyada", "zyaada", "kam", "lagbhag", "kareeb", "kist",
    "kami",
    # Money, accounts, prices.
    "paisa", "paise", "rupaya", "rupaye", "karz", "karza", "qarz", "udhaar",
    "udhar", "udhaari", "byaaj", "vyaaj", "sood", "jama", "rokad", "rokda",
    "nakad", "nagad", "khata", "bahi", "bahikhata", "hisaab", "hisab",
    "lekha", "chittha", "kitab", "goshwara", "bayaan", "suchi", "fehrist",
    "dastavez", "kagaz", "likhat", "adaygi", "chukauti", "bhugtan",
    "keemat", "daam", "mol", "dar", "bhav", "bhaav", "aamdani", "kamai",
    "aay", "vyay", "kharch", "kharcha", "lagat", "nivesh", "poonji",
    "dhan", "daulat", "sampatti", "jaydad", "zameen", "jameen", "laabh",
    "faayda", "fayda", "munafa", "nuksaan", "nuksan", "ghaata", "muft",
    "dalali", "aadhat", "riyayat", "muafi", "katauti", "kaat", "kaata",
    "chhoot",
    # Trade, goods (generic only), places, transport.
    "maal", "samaan", "saman", "saamaan", "cheez", "chiz", "khet", "kheti",
    "kisan", "mazdoor", "pashu", "gaadi", "gadi", "tempo", "thela",
    "bhada", "bhaada", "kiraya", "chungi", "rasta", "raasta", "chakkar",
    "thikana", "pata", "kasba", "gaon", "shahar", "shehar", "desh",
    "videsh", "pardes", "karkhana", "karobaar", "tijarat", "sauda",
    "vyavhaar", "dukaan", "dukan", "godaam", "godam", "vyapaar", "dhanda",
    "aayat", "niryaat", "daftar", "kaam",
    # Quality and disputes.
    "kharab", "kharabi", "ghalat", "ghalti", "galti", "galat",
    "galatfehmi", "phoota", "toota", "khatam", "khatm", "adhoora",
    "adhura", "bekaar", "bekar", "raddi", "kabaad", "kabadi", "kachra",
    "ganda", "maila", "geela", "bheega", "sookha", "khali", "khaali",
    "bhara", "bhari", "saaf", "milavati", "nakli", "farzi", "asli",
    "jaali", "jaal", "keeda", "deemak", "seelan", "phaphundi", "sadan",
    "badbu", "naya", "nayi", "naye", "purana", "purani", "purane",
    "bada", "bade", "badi", "chhota", "chhote", "chhoti", "chota",
    "choti", "lamba", "lambi", "vivaad",
    # Movement of goods and money, communication acts.
    "mila", "mile", "mili", "milega", "milenge", "bheja", "bheji", "bheje",
    "bhejo", "bhejna", "rawana", "rawangi", "nikla", "nikli", "nikle",
    "pahuncha", "pahunchi", "pahunche", "pahunch", "lauta", "lauti",
    "laute", "lautana", "wapas", "wapsi", "chala", "chali", "chale",
    "chal", "chhodo", "chhoda", "likha", "likhi", "likhe", "likh",
    "likho", "likhna", "padh", "padha", "dekha", "dekho", "batao",
    "bataya", "samajh", "samjha", "bola", "dhyaan", "dhyan", "ginti",
    "vajan", "wajan", "jod", "ghata", "ghatao", "bhaag",
    "barabar", "andaza", "suljha", "suljhao", "tay", "dhundh", "dhundho",
    "talash", "khoj", "suraag", "jaanch", "jawab", "sawaal", "sawal",
    "khabar", "chithi", "dastakhat", "mohar", "thappa", "angootha",
    "saboot", "gawah", "halafnama", "arzi", "darkhast", "maang",
    "daava", "shikayat", "naam",
    # Law, threats, fraud, conflict.
    "vakeel", "vakil", "kanoon", "kanooni", "gairkanooni", "niyam", "aain",
    "adalat", "kacheri", "mukadma", "muqadma", "thana", "nyay", "insaaf",
    "jamanat", "zamanat", "muchalka", "jurmana", "harjana", "muavza",
    "faisla", "niptara", "samjhauta", "samadhan", "panchayat", "jhooth",
    "jhootha", "jhoothi", "sach", "dhokha", "dhokebaaz", "fareb", "daga",
    "dagabaazi", "dhandhli", "ghotala", "ghapla", "golmaal", "herapheri",
    "chor", "chori", "dakaiti", "jurm", "mujrim", "rishwat", "jugaad",
    "saazish", "chaal", "veham", "shak", "uljhan", "zimmedar",
    "zimmedari", "jawabdeh", "farz", "zimma", "manzoor", "manjoor",
    "namanzoor", "mansookh", "radd", "dharna", "hadtaal", "hartal",
    "bandh", "talabandi", "virodh", "chetavni", "khabardar", "savdhan",
    "hoshiyar", "dhamki", "khauf", "khatra", "jokhim", "khoon", "jaan",
    "marna", "maro", "khudkushi", "zahar", "zehar", "phaansi", "goli",
    "bandook", "chaku", "lathi", "danda", "thappad", "laat", "dhurt",
    "kamina", "kameena", "harami", "saala", "sala", "bewakoof",
    "besharam", "sharam", "tameez", "badtameezi", "batameezi",
    "gundagardi", "gunda", "ladai", "jhagda", "bahas", "takraar",
    "naraz", "narazgi", "khafa", "gussa", "pareshan", "pareshani",
    "pareshaan", "takleef", "dabaav", "jor", "zabardasti", "majboor",
    "majboori", "bebas", "laachar", "tana", "nakhra", "bartav", "sulook",
    "ravaiya", "masla", "samasya", "dikkat", "sarkar", "theka",
    "thekedaar", "dalal", "munim",
    # Attitudes, feelings, social words.
    "khush", "soch", "fikr", "chinta", "parvah", "parwaah", "daya",
    "reham", "taras", "dard", "bharosa", "aitbar", "yakeen", "neeyat",
    "niyat", "iraada", "irada", "khaas", "sasti", "saste", "mahanga",
    "mehanga", "mehnga", "keemti", "sasta", "mehnat", "koshish", "mazak",
    "pasand", "napasand", "narmi", "sakhti", "tej", "tez", "dheema",
    "aahista", "dheere", "dheela", "dheel", "himmat", "jurrat",
    "gustakhi", "badmashi", "namakharam", "dimaag", "akal", "yaad",
    "bhool", "maafi", "maaf", "upay", "asar", "nateeja", "taraf",
    "andar", "bahar", "upar", "neeche", "peeche", "saamne", "paas",
    "bagal", "pados", "padosi", "rishtedar", "parivar", "ummeed",
    "baddua", "daant", "shukriya", "namaste", "namaskar", "salaam",
    "bhai", "bhaiya", "ehsaan", "kripya", "meherbani", "aaram", "sabar",
    "intezaar", "raah", "tabiyat", "sehat", "beemar", "sankat",
    "museebat", "tabahi", "barbaad", "kangaal", "diwala", "diwaliya",
    "rozi", "rozgaar", "naukri", "pagar", "tankha", "mazdoori",
    "kaabil", "naqaabil", "laayak", "nalayak", "nikamma", "kaamchor",
    "bigad", "marammat", "durust", "sahi", "maan", "sammaan", "izzat",
    "aabru", "saakh", "badnaam", "beizzati", "wada", "aadhar",
    # Habitual and imperative verb forms common in collection talk.
    "karo", "karte", "karta", "karti", "dete", "deta", "deti", "lete",
    "leta", "leti", "jaate", "jaata", "jaati", "jao", "jaoge", "jayega",
    "jayegi", "aate", "aata", "aati", "aao", "aaoge", "rehte", "rehta",
    "rehti", "kehte", "kehta", "kehti", "keh", "kaho", "sunte", "suno",
    "dekhte", "milte", "banta", "bante", "banti", "lagta", "lagte",
    "lagti", "lagao", "lagana", "chalta", "chalte", "chalti", "padta",
    "padte", "padti", "nikalta", "nikalte", "nikalo", "nikal", "daalo",
    "bhag", "bhaga", "bhage", "bhagi", "pakad", "pakdo", "chhod",
    "ruko", "thahro", "intezar", "khoob", "bolo", "bol", "bata",
    "samjhao",
)

CATEGORY_KEYWORDS = {
    "commitment": ("wada", "vada", "karenge", "denge", "de denge", "pay karenge",
                   "bhej denge", "bhar denge", "वादा", "करेंगे", "देंगे", "भेज"),
    "dispute": ("galat", "ghalat", "vivaad", "vivad", "kami", "toota", "phoota",
                "kharab", "ghalti", "गलत", "विवाद", "कमी", "टूटा", "खराब"),
    "haggling": ("mohlat", "samay", "kist", "kisht", "thoda", "thode", "zyada",
                 "baad me", "agli", "मोहलत", "समय", "किस्त", "थोड़ा", "बाद"),
    "anger": ("gussa", "pareshan", "tang", "bakwas", "गुस्सा", "परेशान", "तंग"),
    "legal_threat": ("vakeel", "vakil", "kanooni", "kanuni", "court", "case karenge",
                     "वकील", "कानूनी", "कोर्ट"),
}

DISPUTE_NEGATIONS = {
    "en": ("not part of this request", "remains open"),
    "hi": ("इस अनुरोध का हिस्सा नहीं", "खुला है", "लंबित है"),
    "hinglish": ("is request ka hissa nahi", "is request mein shaamil nahi", "khula hai"),
}


def detect_language(text):
    """Detect en/hi/hinglish. Devanagari share decides Hindi; roman Hindi
    markers decide Hinglish; anything else is English."""
    normalized = normalize_untrusted(text or "")
    if not normalized.strip():
        return "en"
    devanagari = sum(1 for char in normalized if "\u0900" <= char <= "\u097f")
    letters = sum(1 for char in normalized if char.isalpha())
    if letters and devanagari / letters > 0.3:
        return "hi"
    words = set(re.findall(r"[a-z]+", normalized))
    if words & set(HINGLISH_MARKERS):
        return "hinglish"
    return "en"


def classify_multilingual(body):
    """Same intent labels as the English classifier, plus Hindi/Hinglish."""
    from app.services.negotiation import classify_inbound
    if detect_prompt_injection(body or "")[0]:
        return "injection"
    folded = normalize_untrusted(body or "")
    for label, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in folded for keyword in keywords):
            return label
    return classify_inbound(body or "")


def build_message(*, recipient, channel, language, requested_cents, currency,
                  installment_dates, dispute_statement, commitments,
                  source_ids, case_version):
    """Construct the structured message object (facts only, no prose)."""
    if language not in LANGUAGES:
        raise ValueError("Unsupported message language")
    return {"recipient": recipient, "channel": channel, "language": language,
            "requested_cents": int(requested_cents), "currency": currency,
            "installment_dates": list(installment_dates),
            "dispute_statement": dispute_statement,
            "commitments": list(commitments), "source_ids": list(source_ids),
            "case_version": case_version}


def check_message(message, invoice, split, case_version):
    """Pre-render validation of the structured object against server facts."""
    if message["requested_cents"] != split["undisputed_cents"]:
        raise ValueError("Structured message amount differs from server facts")
    if (message["currency"] or "INR") != (invoice.currency or "INR"):
        raise ValueError("Structured message currency differs from the invoice")
    if message["case_version"] != case_version:
        raise ValueError("Structured message targets a stale case version")
    if not message["source_ids"]:
        raise ValueError("Structured message needs at least one source")
    if message["commitments"]:
        raise ValueError("Commitments require explicit staff approval")
    for day in message["installment_dates"]:
        parsed = date.fromisoformat(day)
        if parsed < date.today():
            raise ValueError("Installment dates must not lie in the past")
    if split["disputed_cents"] and not message["dispute_statement"]:
        raise ValueError("Open dispute needs a dispute statement")
    return True


def _money(currency, cents):
    return f"{currency} {Decimal(cents) / Decimal(100):,.2f}"


def render_message(message, invoice_number):
    """Deterministic server-side rendering. Amounts and dates are facts,
    never model output."""
    requested = _money(message["currency"], message["requested_cents"])
    language = message["language"]
    if language == "hi":
        lines = [f"इनवॉइस {invoice_number} के बारे में: कृपया निर्विवादित {requested} का भुगतान करें।"]
        if message["dispute_statement"]:
            lines.append(f"विवादित राशि {message['dispute_statement']}। यह इस अनुरोध का हिस्सा नहीं है।")
    elif language == "hinglish":
        lines = [f"Invoice {invoice_number} ke baare mein: kripya undisputed {requested} ka bhugtan karein."]
        if message["dispute_statement"]:
            lines.append(f"Disputed rashi {message['dispute_statement']}. Ye is request ka hissa nahi hai.")
    else:
        lines = [f"Regarding invoice {invoice_number}, please arrange payment of the undisputed {requested}."]
        if message["dispute_statement"]:
            lines.append(f"Disputed amount {message['dispute_statement']}. It is not part of this request.")
    if message["installment_dates"]:
        dates = ", ".join(message["installment_dates"])
        tail = {"en": f" Instalment dates: {dates}.",
                "hi": f" किस्त की तारीखें: {dates}।",
                "hinglish": f" Kist ki tareekhein: {dates}."}[language]
        lines.append(lines.pop() + tail)
    return "\n".join(lines)


def _amounts_in(text):
    found = re.compile(
        r"(?:\b(?:inr|usd|eur|gbp|rs\.?|rupees)\s*|[₹$€£]\s*)([0-9][0-9,]*(?:\.[0-9]+)?)",
        re.I).findall(text or "")
    values = set()
    for raw in found:
        try:
            values.add(int(Decimal(raw.replace(",", "")) * 100))
        except (ValueError, ArithmeticError):
            continue
    return values


def validate_prose(prose, message, invoice, split, *, allowed_instalments=None):
    """Post-render and approval-time validation of wording against facts."""
    allowed, reason = guard_outbound(
        prose, split["disputed_cents"], split["undisputed_cents"],
        allowed_instalments=allowed_instalments)
    if not allowed:
        raise ValueError(reason or "Outbound guard blocked the wording")
    mentioned = _amounts_in(prose)
    permitted = {split["undisputed_cents"], split["outstanding_cents"],
                 split["invoice_total_cents"]} | set(allowed_instalments or [])
    if message["requested_cents"] not in mentioned and split["undisputed_cents"]:
        raise ValueError("Rendered wording lost the requested amount")
    for extra in mentioned - permitted - {split["disputed_cents"]}:
        raise ValueError(f"Rendered wording contains an unverified amount: {extra}")
    if split["disputed_cents"]:
        negations = DISPUTE_NEGATIONS.get(message["language"], ())
        folded = normalize_untrusted(prose)
        if not any(negation in folded for negation in negations):
            raise ValueError("Rendered wording lost the disputed-versus-undisputed meaning")
    if message["language"] == "hi" and not re.search(r"[\u0900-\u097f]", prose or ""):
        raise ValueError("Hindi wording lost its script")
    for day in message["installment_dates"]:
        if day not in (prose or ""):
            raise ValueError("Rendered wording lost an installment date")
    contact = f"{invoice.counterparty_email or ''} {invoice.counterparty_phone or ''}"
    for match in re.findall(r"[\w.+-]+@[\w.-]+|\+\d[\d\s-]{7,}", prose or ""):
        if match.strip() not in contact:
            raise ValueError("Rendered wording contains an unverified destination")
    return True


FIGURE_LABELS = (
    (r"undisputed", "undisputed_cents"),
    (r"disputed", "disputed_cents"),
    (r"received", "received_cents"),
    (r"total", "invoice_total_cents"),
    (r"\b(balance|remaining|outstanding)\b", "outstanding_cents"),
)


def verify_outbound_body(db, invoice, body, *, allowed_instalments=None):
    """Approval-time check for any stored draft body (any template shape).

    Re-derives server facts at approval time: every stated figure must carry
    the correct label for a current balance, the dispute must stay visibly
    open, and destinations must be on file. Raises with the blocking reason;
    returns True when exact.
    """
    from app.services.receivables import split_balance
    split = split_balance(db, invoice, allow_inconsistent=True)
    if split["reconciliation_error"]:
        raise ValueError("Case needs reconciliation before approval")
    allowed, reason = guard_outbound(
        body, split["disputed_cents"], split["undisputed_cents"],
        allowed_instalments=[split["received_cents"], split["invoice_total_cents"],
                             split["outstanding_cents"], split["disputed_cents"]]
        + list(allowed_instalments or []))
    if not allowed:
        raise ValueError(reason or "Outbound guard blocked the draft")
    pattern = re.compile(
        r"(?:\b(?:inr|usd|eur|gbp|rs\.?|rupees)\s*|[₹$€£]\s*)([0-9][0-9,]*(?:\.[0-9]+)?)",
        re.I)
    followers = r"\s*(?:(?:amount|balance|portion|of|is|:)\s*)*$"
    for match in pattern.finditer(body or ""):
        value = int(Decimal(match.group(1).replace(",", "")) * 100)
        prefix = normalize_untrusted(body[max(0, match.start() - 60):match.start()])
        suffix = normalize_untrusted(body[match.end():match.end() + 30])
        if value in set(allowed_instalments or []):
            continue
        labeled = None
        for label, key in FIGURE_LABELS:
            if re.search(label + followers, prefix) or re.match(
                    r"\s*(?:is|of|:)?\s*" + label + r"\b", suffix):
                labeled = key
                break
        if labeled:
            if value != split[labeled]:
                raise ValueError(f"Draft {labeled} does not match the current ledger")
        elif value not in {split["undisputed_cents"], split["outstanding_cents"]}:
            raise ValueError("Draft amount is not part of the current server balances")
    if split["disputed_cents"]:
        folded = normalize_untrusted(body)
        if not any(negation in folded
                   for negations in DISPUTE_NEGATIONS.values() for negation in negations):
            raise ValueError("Draft must keep the disputed amount visibly open")
    for match in re.findall(r"[\w.+-]+@[\w.-]+|\+\d[\d\s-]{7,}", body or ""):
        contact = f"{invoice.counterparty_email or ''} {invoice.counterparty_phone or ''}"
        if match.strip() not in contact:
            raise ValueError("Draft contains an unverified destination")
    return True
