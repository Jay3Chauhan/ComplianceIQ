"""
Indian financial-regulation acronyms. Expanding them in the query lets BM25 and
the dense model match passages that spell the term out (and vice versa).
"""

import re

GLOSSARY: dict[str, str] = {
    "AA": "Account Aggregator",
    "AIF": "Alternative Investment Fund",
    "AML": "Anti-Money Laundering",
    "AMC": "Asset Management Company",
    "AMFI": "Association of Mutual Funds in India",
    "APR": "Annual Percentage Rate",
    "AUM": "Assets Under Management",
    "BO": "Beneficial Owner",
    "BSBDA": "Basic Savings Bank Deposit Account",
    "CDD": "Customer Due Diligence",
    "CDMDF": "Corporate Debt Market Development Fund",
    "CFT": "Combating Financing of Terrorism",
    "CKYCR": "Central KYC Records Registry",
    "CTR": "Cash Transaction Report",
    "DLA": "Digital Lending App",
    "DP": "Depository Participant",
    "EDD": "Enhanced Due Diligence",
    "ETF": "Exchange Traded Fund",
    "FATF": "Financial Action Task Force",
    "FIP": "Financial Information Provider",
    "FIU": "Financial Information User",
    "FIU-IND": "Financial Intelligence Unit India",
    "FLDG": "First Loss Default Guarantee",
    "FoF": "Fund of Funds",
    "KFS": "Key Fact Statement",
    "KIM": "Key Information Memorandum",
    "KYC": "Know Your Customer",
    "LSP": "Lending Service Provider",
    "MF": "Mutual Fund",
    "MTF": "Margin Trading Facility",
    "NAV": "Net Asset Value",
    "NBFC": "Non-Banking Financial Company",
    "NBFC-AA": "Non-Banking Financial Company Account Aggregator",
    "NFO": "New Fund Offer",
    "NOF": "Net Owned Fund",
    "NRI": "Non-Resident Indian",
    "OVD": "Officially Valid Document",
    "PAN": "Permanent Account Number",
    "PEP": "Politically Exposed Person",
    "PIO": "Person of Indian Origin",
    "PML": "Prevention of Money Laundering",
    "PMLA": "Prevention of Money Laundering Act",
    "RE": "Regulated Entity",
    "SAR": "Suspicious Activity Report",
    "SCORES": "SEBI Complaints Redress System",
    "SID": "Scheme Information Document",
    "SIP": "Systematic Investment Plan",
    "STR": "Suspicious Transaction Report",
    "SWP": "Systematic Withdrawal Plan",
    "TER": "Total Expense Ratio",
    "UBO": "Ultimate Beneficial Owner",
    "UCC": "Unique Client Code",
    "V-CIP": "Video-based Customer Identification Process",
}

_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z\-]{0,7}\b")


def expand_query(query: str) -> str:
    """Appends expansions for acronyms that appear (case-sensitive) in the query."""
    additions: list[str] = []
    lowered = query.lower()
    for token in dict.fromkeys(_TOKEN_RE.findall(query)):
        expansion = GLOSSARY.get(token)
        if expansion and expansion.lower() not in lowered:
            additions.append(f"{expansion} ({token})")
    return f"{query} [{'; '.join(additions)}]" if additions else query
