"""Create the sample spreadsheets people can try on the upload screen.

Run from the TableTalk folder:
    uv run python -m scripts.make_sample_datasets

Writes three Excel files into samples/, each with 3 linked sheets:
    shop_data.xlsx    an online shop: customers, products, orders
    bank_fraud.xlsx   a bank: accounts, merchants, card transactions (some fraud)
    school_data.xlsx  a school: students, courses, enrollments with scores

Every file uses a fixed random seed, so it comes out the same every time.
Linking columns share the same name across sheets (for example "Customer ID"),
which is how TableTalk finds the relationships for the data map.
"""

import random
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

OUT = Path("samples")

FIRST = ["Aisha", "Ben", "Chloe", "Dev", "Emma", "Farhan", "Grace", "Hiro", "Isla", "Jai",
         "Kiran", "Leo", "Maya", "Nikhil", "Olivia", "Priya", "Rohan", "Sara", "Tanvi", "Zoe"]
LAST = ["Sharma", "Smith", "Patel", "Brown", "Khan", "Wilson", "Gupta", "Taylor", "Singh", "Lee"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "London", "Toronto", "New York"]


def person(rng):
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def save(path, sheets):
    OUT.mkdir(exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    sizes = ", ".join(f"{len(df)} {name.lower()}" for name, df in sheets.items())
    print(f"Created {path} ({sizes})")


# ---------- 1. online shop ----------

def make_shop():
    rng = random.Random(42)
    customers = pd.DataFrame({
        "Customer ID": range(1, 31),
        "Name": [person(rng) for _ in range(30)],
        "City": [rng.choice(CITIES) for _ in range(30)],
        "Signup Date": [date(2025, 1, 1) + timedelta(days=rng.randint(0, 600)) for _ in range(30)],
    })
    products = pd.DataFrame({
        "Product ID": range(101, 111),
        "Product Name": ["Laptop", "Mouse", "Keyboard", "Monitor", "Headphones",
                         "Webcam", "Desk Lamp", "USB Hub", "Phone Stand", "Backpack"],
        "Category": ["Electronics", "Accessories", "Accessories", "Electronics", "Audio",
                     "Electronics", "Home", "Accessories", "Accessories", "Bags"],
        "Price": [899.0, 19.5, 45.0, 229.0, 79.0, 59.0, 34.0, 25.0, 15.0, 65.0],
    })
    orders = pd.DataFrame({
        "Order ID": range(1001, 1101),
        "Customer ID": [rng.randint(1, 30) for _ in range(100)],
        "Product ID": [rng.randint(101, 110) for _ in range(100)],
        "Quantity": [rng.randint(1, 5) for _ in range(100)],
        "Order Date": [date(2026, 1, 1) + timedelta(days=rng.randint(0, 300)) for _ in range(100)],
        "Status": [rng.choice(["Delivered", "Shipped", "Cancelled", "Pending"]) for _ in range(100)],
    })
    save(OUT / "shop_data.xlsx", {"Customers": customers, "Products": products, "Orders": orders})


# ---------- 2. bank card fraud ----------

def make_fraud():
    rng = random.Random(7)
    n_accounts, n_tx = 40, 300

    accounts = pd.DataFrame({
        "Account ID": [f"AC{1000 + i}" for i in range(n_accounts)],
        "Holder Name": [person(rng) for _ in range(n_accounts)],
        "Home City": [rng.choice(CITIES) for _ in range(n_accounts)],
        "Account Type": [rng.choice(["Savings", "Current", "Credit"]) for _ in range(n_accounts)],
        "Opened On": [date(2020, 1, 1) + timedelta(days=rng.randint(0, 2000)) for _ in range(n_accounts)],
    })

    merchant_rows = [
        ("Fresh Mart", "Groceries", "India"), ("City Fuel", "Fuel", "India"),
        ("Byte Store", "Electronics", "India"), ("Cafe Mocha", "Restaurants", "India"),
        ("Book Nook", "Books", "Canada"), ("Maple Grocers", "Groceries", "Canada"),
        ("Sky Travels", "Travel", "UK"), ("Lux Watches", "Jewellery", "UAE"),
        ("QuickBet Online", "Gambling", "Malta"), ("GiftCard Hub", "Gift cards", "Cyprus"),
        ("Stream Plus", "Subscriptions", "USA"), ("Pharma Care", "Pharmacy", "India"),
    ]
    merchants = pd.DataFrame({
        "Merchant ID": [f"M{200 + i}" for i in range(len(merchant_rows))],
        "Merchant Name": [m[0] for m in merchant_rows],
        "Category": [m[1] for m in merchant_rows],
        "Country": [m[2] for m in merchant_rows],
    })
    risky = set(merchants.loc[merchants["Category"].isin(["Jewellery", "Gambling", "Gift cards"]), "Merchant ID"])
    normal = [m for m in merchants["Merchant ID"] if m not in risky]

    rows = []
    start = datetime(2026, 9, 1)
    for i in range(n_tx):
        account = rng.choice(accounts["Account ID"].tolist())
        fraud = rng.random() < 0.06
        if fraud:
            # Fraud pattern: risky merchant, large amount, late at night, mostly online
            merchant = rng.choice(sorted(risky))
            amount = round(rng.uniform(800, 5000), 2)
            when = start + timedelta(days=rng.randint(0, 60), hours=rng.choice([0, 1, 2, 3, 4]), minutes=rng.randint(0, 59))
            channel = rng.choice(["Online", "Online", "Card present"])
        else:
            merchant = rng.choice(normal)
            amount = round(rng.uniform(3, 400), 2)
            when = start + timedelta(days=rng.randint(0, 60), hours=rng.randint(7, 22), minutes=rng.randint(0, 59))
            channel = rng.choice(["Card present", "Card present", "Online", "ATM"])
        rows.append((f"T{50000 + i}", account, merchant, amount, when, channel, "Yes" if fraud else "No"))

    transactions = pd.DataFrame(rows, columns=["Transaction ID", "Account ID", "Merchant ID", "Amount",
                                               "Transaction Time", "Channel", "Is Fraud"])
    transactions = transactions.sort_values("Transaction Time").reset_index(drop=True)
    save(OUT / "bank_fraud.xlsx", {"Accounts": accounts, "Merchants": merchants, "Transactions": transactions})


# ---------- 3. school ----------

def make_school():
    rng = random.Random(11)
    n_students = 40

    students = pd.DataFrame({
        "Student ID": [f"S{300 + i}" for i in range(n_students)],
        "Student Name": [person(rng) for _ in range(n_students)],
        "Grade Level": [rng.choice([9, 10, 11, 12]) for _ in range(n_students)],
        "City": [rng.choice(CITIES) for _ in range(n_students)],
    })
    course_rows = [
        ("Algebra", "Maths", "Ms Rao"), ("Geometry", "Maths", "Mr Clark"),
        ("Physics", "Science", "Dr Iyer"), ("Chemistry", "Science", "Ms Lopez"),
        ("Biology", "Science", "Mr Mehta"), ("World History", "Humanities", "Ms Brown"),
        ("English Literature", "Languages", "Mr Ahmed"), ("Computer Science", "Technology", "Ms Kim"),
    ]
    courses = pd.DataFrame({
        "Course ID": [f"C{10 + i}" for i in range(len(course_rows))],
        "Course Name": [c[0] for c in course_rows],
        "Subject": [c[1] for c in course_rows],
        "Teacher": [c[2] for c in course_rows],
    })

    rows, n = [], 0
    for sid in students["Student ID"]:
        ability = rng.uniform(55, 92)          # some students do better overall
        for cid in rng.sample(courses["Course ID"].tolist(), 4):
            n += 1
            attendance = round(min(100, max(50, rng.gauss(88, 8))), 1)
            score = round(min(100, max(20, ability + (attendance - 88) * 0.6 + rng.gauss(0, 8))), 1)
            rows.append((f"E{n:04d}", sid, cid, rng.choice(["Fall 2025", "Spring 2026"]), score, attendance))

    enrollments = pd.DataFrame(rows, columns=["Enrollment ID", "Student ID", "Course ID", "Term",
                                              "Score", "Attendance Percent"])
    save(OUT / "school_data.xlsx", {"Students": students, "Courses": courses, "Enrollments": enrollments})


if __name__ == "__main__":
    make_shop()
    make_fraud()
    make_school()
    print("Done. Restart the backend if it is running, then pick a sample on the upload screen.")
