"""Lease clause text templates. Risk-adverse clause types appear more often on
leases that later default, giving the clause features real signal."""

from __future__ import annotations

CLAUSE_TEMPLATES: dict[str, list[str]] = {
    "early_termination": [
        "Tenant may terminate this Lease at any time after the {n}th month of the Term "
        "upon ninety (90) days written notice and payment of unamortized concessions.",
        "Either party may terminate upon one hundred eighty (180) days notice following "
        "the {n}th month anniversary of the Commencement Date.",
    ],
    "co_tenancy": [
        "If the Anchor Tenant ceases operations for more than ninety (90) days, Tenant's "
        "Base Rent shall abate to {n} percent of the stated amount until replaced.",
        "Tenant's obligation to operate is conditioned on at least {n} percent of the "
        "Shopping Center GLA being open and operating.",
    ],
    "exclusive_use": [
        "Landlord shall not lease space within the Project to any business whose primary "
        "use competes with Tenant's Permitted Use as defined in Section {n}.",
    ],
    "gross_up": [
        "Operating Expenses for any calendar year in which occupancy is less than "
        "{n} percent shall be grossed up to reflect {n} percent occupancy.",
    ],
    "expansion_option": [
        "Tenant shall have a one-time Right of First Offer on contiguous space on the "
        "{n}th floor, exercisable within ten (10) business days of Landlord's notice.",
    ],
    "renewal_option": [
        "Tenant may extend the Term for one (1) additional period of {n} years at "
        "ninety-five percent (95%) of Fair Market Rent.",
    ],
    "security_substitution": [
        "Tenant may substitute the cash Security Deposit with a Letter of Credit reducing "
        "by {n} percent annually, subject to no Event of Default having occurred.",
    ],
    "assignment": [
        "Tenant may assign this Lease to an affiliate without Landlord consent provided "
        "the assignee's tangible net worth exceeds {n} million dollars.",
    ],
}

# clause types correlated with later distress (weak commitments, abatement rights)
ADVERSE_CLAUSE_TYPES = ("early_termination", "co_tenancy", "security_substitution")
BENIGN_CLAUSE_TYPES = tuple(t for t in CLAUSE_TEMPLATES if t not in ADVERSE_CLAUSE_TYPES)
