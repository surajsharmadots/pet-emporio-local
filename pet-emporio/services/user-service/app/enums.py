import enum


class UserType(str, enum.Enum):
    customer = "customer"
    seller = "seller"
    doctor = "doctor"
    lab_technician = "lab_technician"
    groomer = "groomer"
    pharmacist = "pharmacist"
    admin = "admin"
    super_admin = "super_admin"


class Gender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class TenantType(str, enum.Enum):
    seller = "seller"
    pharmacy = "pharmacy"
    doctor = "doctor"
    lab = "lab"
    groomer = "groomer"


class TenantStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"
    rejected = "rejected"


class TenantPlan(str, enum.Enum):
    basic = "basic"
    premium = "premium"
    enterprise = "enterprise"


class KycDocType(str, enum.Enum):
    aadhaar = "aadhaar"
    pan = "pan"
    gst = "gst"
    driving_license = "driving_license"
    bank_statement = "bank_statement"
    shop_act = "shop_act"


class KycStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class OnboardingStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PortalType(str, enum.Enum):
    doctor = "doctor"
    lab = "lab"
    seller = "seller"
    pharmacy = "pharmacy"
    groomer = "groomer"