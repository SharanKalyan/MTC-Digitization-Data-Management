import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

# =================================================
# GLOBAL DATE STANDARDS (DO NOT CHANGE)
# =================================================
DATE_FMT = "%d/%m/%Y"
DATETIME_FMT = "%d/%m/%Y %H:%M"

# -------------------------------------------------
# Page Configuration
# -------------------------------------------------
st.set_page_config(page_title="Monisha Tiffin Center", layout="centered")

# -------------------------------------------------
# PIN Protection
# -------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("### 🔒 Enter PIN to Access")

    with st.form("pin_form"):
        pin = st.text_input("PIN", type="password", max_chars=6)
        submit = st.form_submit_button("➡️ Enter")

    if submit:
        if pin == st.secrets["security"]["app_pin"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect PIN ❌")

    st.stop()

# -------------------------------------------------
# Google Sheets Connection
# -------------------------------------------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

CREDS = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["gcp_service_account"], SCOPE
)

client = gspread.authorize(CREDS)
spreadsheet = client.open("MTC-Digitization")

expense_sheet = spreadsheet.sheet1
attendance_sheet = spreadsheet.worksheet("Attendance")
sales_sheet = spreadsheet.worksheet("Sales")
balance_sheet = spreadsheet.worksheet("Daily_Balance")

# -------------------------------------------------
# Time Handling (IST)
# -------------------------------------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.now(ist)

today_date = now.date()
today_str = today_date.strftime(DATE_FMT)
now_str = now.strftime(DATETIME_FMT)


# =================================================
# 🔁 DAILY BALANCE UPSERT HELPER
# =================================================
def upsert_daily_balance(
    balance_sheet,
    target_date,
    delta_sales=0.0,
    delta_expense=0.0,
    now_str=""
):
    import pandas as pd

    date_str = target_date.strftime(DATE_FMT)

    records = balance_sheet.get_all_records()
    df = pd.DataFrame(records)

    # -------------------------------------------------
    # If sheet is empty → first ever entry
    # -------------------------------------------------
    if df.empty:
        opening_balance = 0.0
        total_sales = float(delta_sales)
        total_expense = float(delta_expense)
        closing_balance = opening_balance + total_sales - total_expense

        balance_sheet.append_row([
            date_str,
            opening_balance,
            total_sales,
            total_expense,
            closing_balance,
            now_str
        ])
        return

    # -------------------------------------------------
    # Normalize date column
    # -------------------------------------------------
    df["Date"] = pd.to_datetime(df["Date"], format=DATE_FMT, errors="coerce")
    target_dt = pd.to_datetime(target_date)

    # -------------------------------------------------
    # CASE 1: DATE EXISTS → UPDATE
    # -------------------------------------------------
    if target_dt in df["Date"].values:

        row_idx = df.index[df["Date"] == target_dt][0] + 2

        opening_balance = float(df.loc[row_idx - 2, "Opening Balance"])
        total_sales = float(df.loc[row_idx - 2, "Total Sales"]) + float(delta_sales)
        total_expense = float(df.loc[row_idx - 2, "Total Expense"]) + float(delta_expense)

        closing_balance = opening_balance + total_sales - total_expense

        balance_sheet.update(f"C{row_idx}", [[total_sales]])
        balance_sheet.update(f"D{row_idx}", [[total_expense]])
        balance_sheet.update(f"E{row_idx}", [[closing_balance]])
        balance_sheet.update(f"F{row_idx}", [[now_str]])

        return

    # -------------------------------------------------
    # CASE 2: DATE DOES NOT EXIST → INSERT
    # -------------------------------------------------
    prev_days = df[df["Date"] < target_dt]

    if not prev_days.empty:
        opening_balance = float(
            prev_days.sort_values("Date").iloc[-1]["Closing Balance"]
        )
    else:
        opening_balance = 0.0

    total_sales = float(delta_sales)
    total_expense = float(delta_expense)
    closing_balance = opening_balance + total_sales - total_expense

    balance_sheet.append_row([
        date_str,
        opening_balance,
        total_sales,
        total_expense,
        closing_balance,
        now_str
    ])



# -------------------------------------------------
# Navigation
# -------------------------------------------------
section = st.selectbox(
    "📢 Select Section",
    [
        "📊 Today's Summary",
        "🧾 Expense Entry",
        "💰 Sales Entry",
        "👤 Employee Salary",
        "🧑‍🍳 Attendance",
        "📊 Expense Analytics",
        "📈 Attendance Analytics",
        "📊 Sales Analytics",
    ],
)

# =================================================
# 📊 TODAY'S SUMMARY
# =================================================
if section == "📊 Today's Summary":

    st.markdown("## 📊 Today's Summary")

    # ---------- SALES ----------
    sales_df = pd.DataFrame(sales_sheet.get_all_records())
    if not sales_df.empty:
        sales_df["Cash Total"] = pd.to_numeric(sales_df["Cash Total"], errors="coerce")
        sales_df["date"] = pd.to_datetime(
            sales_df["Date"], format=DATE_FMT, errors="coerce"
        ).dt.date
        total_sales_today = sales_df[sales_df["date"] == today_date]["Cash Total"].sum()
    else:
        total_sales_today = 0.0

    # ---------- EXPENSE ----------
    expense_df = pd.DataFrame(expense_sheet.get_all_records())
    if not expense_df.empty:
        expense_df["Expense Amount"] = pd.to_numeric(
            expense_df["Expense Amount"], errors="coerce"
        )
        expense_df["date"] = pd.to_datetime(
            expense_df["Date & Time"], format=DATETIME_FMT, errors="coerce"
        ).dt.date
        total_expense_today = expense_df[
            expense_df["date"] == today_date
        ]["Expense Amount"].sum()
    else:
        total_expense_today = 0.0

   # ---------- OPENING BALANCE ----------
    balance_df = pd.DataFrame(balance_sheet.get_all_records())
    
    if not balance_df.empty:
        balance_df["date"] = pd.to_datetime(
            balance_df["Date"],
            format=DATE_FMT,
            errors="coerce"
        )
    
        today_dt = pd.to_datetime(today_date)
    
        prev_days = balance_df[balance_df["date"] < today_dt]
    
        opening_balance = (
            int(prev_days.sort_values("date").iloc[-1]["Closing Balance"])
            if not prev_days.empty else 0
        )
    else:
        opening_balance = 0


    closing_balance = opening_balance + total_sales_today - total_expense_today

    st.metric("📥 Opening Balance", f"₹ {opening_balance:,.0f}")
    st.metric("💵 Total Sales Today", f"₹ {total_sales_today:,.0f}")
    st.metric("💸 Total Expense Today", f"₹ {total_expense_today:,.0f}")
    st.metric("💰 Balance Remaining Today", f"₹ {closing_balance:,.0f}")

    # ---------- SAVED CLOSING BALANCE (FROM DAILY_BALANCE) ----------
    saved_closing = None
    saved_ts = None
    
    if not balance_df.empty:
        today_row = balance_df[
            balance_df["date"] == today_dt
        ]
    
        if not today_row.empty:
            saved_closing = float(today_row.iloc[0]["Closing Balance"])
            saved_ts = today_row.iloc[0]["Entry Timestamp"]
    
    # ---------- UI ----------
    if saved_closing is not None:
        st.metric(
            "📦 Closing Balance (Saved)",
            f"₹ {saved_closing:,.0f}"
        )
        st.caption(f"Last updated: {saved_ts}")
    else:
        st.metric(
            "📦 Closing Balance (Saved)",
            "Not saved yet"
        )
        st.caption("No closing balance recorded for today")


# =================================================
# 🧾 EXPENSE ENTRY (BULK)
# =================================================
elif section == "🧾 Expense Entry":

    st.markdown("## 🧾 Expense Entry")

    EXPENSE_CATEGORIES = [
        "Groceries","Vegetables","Gas","Oil & Ghee","Non-Veg",
        "Milk","Banana Leaf","Maintenance","Electricity",
        "Rent","Salary and Advance","Transportation","Others"
    ]

    with st.form("expense_form"):
        exp_date = st.date_input("Expense Date", value=today_date)
        exp_time = st.time_input("Expense Time", value=now.time().replace(second=0))
        exp_dt = datetime.combine(exp_date, exp_time).strftime(DATETIME_FMT)
        st.markdown("---")

        expense_rows = []

        for cat in EXPENSE_CATEGORIES:
            sel = st.checkbox(cat, key=f"sel_{cat}")
            sub = st.text_input("Sub-category", key=f"sub_{cat}")
            amt = st.number_input("Amount", min_value=0, key=f"amt_{cat}")
            pay = st.selectbox("Payment", ["Cash","UPI","Cheque"], key=f"pay_{cat}")
            by = st.selectbox("Expense By", ["RK","AR","YS"], key=f"by_{cat}")
            expense_rows.append((sel, cat, sub, amt, pay, by))
            st.markdown("---")

        submit = st.form_submit_button("✅ Submit")

    if submit:
        count = 0
        total_expense_added = 0.0

        for sel, cat, sub, amt, pay, by in expense_rows:
            if sel and amt > 0:
                expense_sheet.append_row([
                    exp_dt, cat, sub, amt, pay, by
                ])
                total_expense_added += float(amt)
                count += 1
    
        if total_expense_added > 0:
            upsert_daily_balance(
                balance_sheet=balance_sheet,
                target_date=exp_date,
                delta_expense=total_expense_added,
                now_str=now_str
            )
    
        st.success(f"{count} expense(s) recorded" if count else "No expenses submitted")

# =================================================
# 👤 EMPLOYEE SALARY / ADVANCE
# =================================================
elif section == "👤 Employee Salary":

    st.markdown("## 👤 Employee Salary / Advance")

    EMPLOYEES = [
        "Vinoth","Ravi","Mani","Ansari","Kumar","Sakthi","Vijaya","Hari",
        "Samuthuram","Ramesh","Punitha","Vembu","Babu","Latha",
        "Indhra","Ambika","RY","YS","Poosari","Balaji"
    ]

    with st.form("salary_form"):

        sal_date = st.date_input("Payment Date", value=today_date)
        sal_time = st.time_input(
            "Payment Time",
            value=now.time().replace(second=0)
        )

        sal_dt = datetime.combine(sal_date, sal_time).strftime(DATETIME_FMT)

        st.markdown("---")
        st.markdown("### 💼 Salary / Advance Payments")

        salary_rows = []

        for emp in EMPLOYEES:
            col1, col2, col3 = st.columns([2, 2, 2])

            with col1:
                sel = st.checkbox(emp, key=f"sal_{emp}")

            with col2:
                pay_type = st.selectbox(
                    "Type",
                    ["Salary", "Advance"],
                    key=f"type_{emp}"
                )

            with col3:
                amount = st.number_input(
                    "Amount",
                    min_value=0.0,
                    step=500.0,
                    key=f"amt_{emp}"
                )

            salary_rows.append((sel, emp, pay_type, amount))

        submit = st.form_submit_button("✅ Save Salary Payments")

    # ---------------- SAVE LOGIC ----------------
    if submit:
        count = 0
        total_salary_paid = 0.0

        for sel, emp, pay_type, amount in salary_rows:
            if sel and amount > 0:
                expense_sheet.append_row([
                    sal_dt,
                    "Salary and Advance",     # Category
                    emp,                      # Sub-Category = Employee
                    amount,
                    "Cash",                   # Payment Mode (fixed)
                    pay_type                  # Expense By reused as Type
                ])

                total_salary_paid += float(amount)
                count += 1

        # 🔁 Update Daily Balance
        if total_salary_paid > 0:
            upsert_daily_balance(
                balance_sheet=balance_sheet,
                target_date=sal_date,
                delta_expense=total_salary_paid,
                now_str=now_str
            )

        st.success(
            f"✅ {count} salary / advance payment(s) recorded"
            if count else
            "No salary payments recorded"
        )
    


# =================================================
# 💰 SALES ENTRY (BULK – FIXED STRUCTURE)
# =================================================
elif section == "💰 Sales Entry":

    st.markdown("## 💰 Sales Entry")

    with st.form("sales_form"):

        sale_date = st.date_input(
            "Sale Date",
            value=today_date
        )

        sale_date_str = sale_date.strftime(DATE_FMT)

        st.markdown("### 🏪 Store-wise Sales Entry")

        # ---------- Bigstreet ----------
        st.markdown("**Bigstreet**")
        col1, col2 = st.columns(2)
        big_morning = col1.number_input(
            "Morning Sales",
            min_value=0.0,
            step=100.0,
            key="big_morning"
        )
        big_night = col2.number_input(
            "Night Sales",
            min_value=0.0,
            step=100.0,
            key="big_night"
        )

        st.markdown("---")

        # ---------- Main ----------
        st.markdown("**Main Store (Full Day)**")
        main_full = st.number_input(
            "Main Store Sales",
            min_value=0.0,
            step=100.0,
            key="main_full"
        )

        st.markdown("---")

        # ---------- Orders ----------
        st.markdown("**Orders (Full Day)**")
        orders_full = st.number_input(
            "Orders Sales",
            min_value=0.0,
            step=100.0,
            key="orders_full"
        )

        submit = st.form_submit_button("✅ Submit Sales")

    # =================================================
    # SAVE LOGIC
    # =================================================
    if submit:

        sales_rows = [
            ("Bigstreet", "Morning", big_morning),
            ("Bigstreet", "Night", big_night),
            ("Main", "Full Day", main_full),
            ("Orders", "Full Day", orders_full),
        ]

        total_sales_added = 0.0
        rows_written = 0

        existing_rows = sales_sheet.get_all_values() or []

        for store, slot, amount in sales_rows:

            if amount and amount > 0:
                safe_amount = round(float(amount), 2)

                # ---------- Remove existing entry for same date/store/slot ----------
                for i in reversed([
                    idx for idx, r in enumerate(existing_rows[1:], start=2)
                    if r[0] == sale_date_str and r[1] == store and r[2] == slot
                ]):
                    sales_sheet.delete_rows(i)

                # ---------- Append new row ----------
                sales_sheet.append_row([
                    str(sale_date_str),
                    str(store),
                    str(slot),
                    safe_amount,
                    str(now_str)
                ])

                total_sales_added += safe_amount
                rows_written += 1

        # ---------- Update Daily Balance ----------
        if total_sales_added > 0:
            upsert_daily_balance(
                balance_sheet=balance_sheet,
                target_date=sale_date,
                delta_sales=total_sales_added,
                now_str=now_str
            )

        st.success(f"✅ {rows_written} sales entries recorded successfully")


# =================================================
# 🧑‍🍳 ATTENDANCE
# =================================================
elif section == "🧑‍🍳 Attendance":

    st.markdown("## 🧑‍🍳 Attendance")

    EMPLOYEES = [
        "Vinoth","Ravi","Mani","Ansari","Kumar","Sakthi","Vijaya","Hari",
        "Samuthuram","Ramesh","Punitha","Vembu","Babu","Latha",
        "Indhra","Ambika","RY","YS","Poosari","Balaji"
    ]

    att_date = st.date_input(
        "Attendance Date",
        value=today_date
    ).strftime(DATE_FMT)

    st.markdown("---")

    # =================================================
    # 🌅 MORNING SHIFT
    # =================================================
    st.subheader("🌅 Morning")

    morning = {}
    for e in EMPLOYEES:
        morning[e] = st.checkbox(e, key=f"m_{e}")

    st.markdown("---")

    # =================================================
    # 🌙 NIGHT SHIFT
    # =================================================
    st.subheader("🌙 Night")

    night = {}
    for e in EMPLOYEES:
        night[e] = st.checkbox(e, key=f"n_{e}")

    st.markdown("---")

    # =================================================
    # ✅ SUBMIT
    # =================================================
    if st.button("✅ Submit Attendance"):

        # Remove existing entries for this date
        rows = attendance_sheet.get_all_values()
        for i in reversed([
            idx for idx, r in enumerate(rows[1:], start=2)
            if r[0] == att_date
        ]):
            attendance_sheet.delete_rows(i)

        # Insert fresh records
        for e in EMPLOYEES:
            attendance_sheet.append_row([
                att_date,
                e,
                "✖" if morning[e] else "✔",
                "✖" if night[e] else "✔",
                now_str
            ])

        st.success("Attendance saved ✅")


# =================================================
# 📊 EXPENSE ANALYTICS (TABLE-ONLY + KPIs)
# =================================================
elif section == "📊 Expense Analytics":

    st.markdown("## 📊 Expense Analytics")

    df = pd.DataFrame(expense_sheet.get_all_records())
    if df.empty:
        st.info("No expense data available yet.")
        st.stop()

    # -------------------------------------------------
    # Data Cleaning & Date Normalization
    # -------------------------------------------------
    df["Expense Amount"] = pd.to_numeric(df["Expense Amount"], errors="coerce")

    df["datetime"] = pd.to_datetime(
        df["Date & Time"],
        format=DATETIME_FMT,      # DD/MM/YYYY HH:MM
        errors="coerce"
    )

    df = df.dropna(subset=["datetime", "Expense Amount"])

    # 🔑 Normalize once — reuse everywhere
    df["date"] = df["datetime"].dt.date
    df["year"] = df["datetime"].dt.year
    df["month"] = df["datetime"].dt.month
    df["week"] = df["datetime"].dt.isocalendar().week

    current_year = now.year
    current_month = now.month
    current_week = now.isocalendar().week

    # =================================================
    # 📌 EXPENSE KPI SUMMARY
    # =================================================
    overall_expense = df["Expense Amount"].sum()

    monthly_expense = df[
        (df["year"] == current_year) &
        (df["month"] == current_month)
    ]["Expense Amount"].sum()

    weekly_expense = df[
        (df["year"] == current_year) &
        (df["week"] == current_week)
    ]["Expense Amount"].sum()

    col1, col2, col3 = st.columns(3)

    col1.metric("💸 Overall Expenses", f"₹ {overall_expense:,.0f}")
    col2.metric("📅 Expenses (This Month)", f"₹ {monthly_expense:,.0f}")
    col3.metric("🗓️ Expenses (This Week)", f"₹ {weekly_expense:,.0f}")

    st.markdown("---")

    # =================================================
    # 1️⃣ Category-wise Expense
    # =================================================
    st.subheader("📂 Category-wise Expense")

    cat_expense = (
        df.groupby("Category", as_index=False)["Expense Amount"]
        .sum()
        .sort_values("Expense Amount", ascending=False)
        .reset_index(drop=True)
    )

    st.dataframe(cat_expense, use_container_width=True)

    # =================================================
    # 🧾 Other Expenses – Sub-Category Breakdown
    # =================================================
    st.subheader("🧾 Other Expenses Breakdown")
    
    other_df = df[df["Category"] == "Others"].copy()
    
    if other_df.empty:
        st.info("No 'Other' expenses recorded yet.")
    else:
        # 🔑 Normalize missing sub-categories
        other_df["Sub-Category"] = (
            other_df["Sub-Category"]
            .fillna("")
            .str.strip()
            .replace("", "Miscellaneous Expenses")
        )
    
        other_summary = (
            other_df
            .groupby("Sub-Category", as_index=False)["Expense Amount"]
            .sum()
            .sort_values("Expense Amount", ascending=False)
            .reset_index(drop=True)
        )
    
        st.dataframe(other_summary, use_container_width=True)
    
    st.markdown("---")

    # =================================================
    # 👤 Employee-wise Salary Paid
    # =================================================
    st.subheader("👤 Employee-wise Salary / Advance Paid")
    
    salary_df = df[df["Category"] == "Salary and Advance"]
    
    if salary_df.empty:
        st.info("No salary payments recorded yet.")
    else:
        salary_summary = (
            salary_df
            .groupby("Sub-Category", as_index=False)["Expense Amount"]
            .sum()
            .rename(columns={
                "Sub-Category": "Employee",
                "Expense Amount": "Total Paid"
            })
            .sort_values("Total Paid", ascending=False)
            .reset_index(drop=True)
        )
    
        st.dataframe(salary_summary, use_container_width=True)
    
    st.markdown("---")



    # =================================================
    # 2️⃣ Expense Trend (CURRENT MONTH ONLY)
    # =================================================
    st.subheader("📈 Expense Trend (Current Month)")
    
    trend = st.radio(
        "Trend Type",
        ["Daily", "Weekly", "Monthly"],
        horizontal=True
    )
    
    # Filter once — reuse everywhere
    month_df = df[
        (df["year"] == current_year) &
        (df["month"] == current_month)
    ]
    
    if trend == "Daily":
        # ✅ Daily expenses — CURRENT MONTH ONLY
        trend_df = (
            month_df
            .groupby("date", as_index=False)["Expense Amount"]
            .sum()
            .rename(columns={"date": "Date"})
            .sort_values("Date", ascending=False)
            .reset_index(drop=True)
        )
    
        trend_df["Date"] = trend_df["Date"].apply(
            lambda x: x.strftime(DATE_FMT)
        )
    
    elif trend == "Weekly":
        # ✅ Weekly expenses — CURRENT MONTH ONLY (ISO week)
        trend_df = (
            month_df
            .groupby("week", as_index=False)["Expense Amount"]
            .sum()
            .rename(columns={"week": "Week (ISO)"})
            .sort_values("Week (ISO)", ascending=False)
            .reset_index(drop=True)
        )
    
    else:  # Monthly
        # ✅ Monthly trend — YEAR-WISE (this one is okay to be broader)
        trend_df = (
            df.groupby(["year", "month"], as_index=False)["Expense Amount"]
            .sum()
            .rename(columns={"month": "Month"})
            .sort_values(["year", "Month"], ascending=False)
            .reset_index(drop=True)
        )
    
    st.dataframe(trend_df, use_container_width=True)
    st.markdown("---")

    # =================================================
    # 3️⃣ Payment Mode-wise Expense
    # =================================================
    st.subheader("💳 Payment Mode")

    payment_df = (
        df.groupby("Payment Mode", as_index=False)["Expense Amount"]
        .sum()
        .sort_values("Expense Amount", ascending=False)
        .reset_index(drop=True)
    )

    st.dataframe(payment_df, use_container_width=True)

    st.markdown("---")

    # =================================================
    # 4️⃣ Expense By
    # =================================================
    st.subheader("👤 Expense By")

    by_df = (
        df.groupby("Expense By", as_index=False)["Expense Amount"]
        .sum()
        .sort_values("Expense Amount", ascending=False)
        .reset_index(drop=True)
    )

    st.dataframe(by_df, use_container_width=True)



# =================================================
# 📈 ATTENDANCE ANALYTICS
# =================================================
elif section == "📈 Attendance Analytics":

    st.markdown("## 📈 Attendance Analytics")

    records = attendance_sheet.get_all_records()
    if not records:
        st.info("No attendance data available yet.")
        st.stop()

    df = pd.DataFrame(records)

    # -------------------------------------------------
    # Date Cleaning (DD/MM/YYYY)
    # -------------------------------------------------
    df["date"] = pd.to_datetime(
        df["Date"],
        format=DATE_FMT,
        errors="coerce"
    )

    df = df.dropna(subset=["date"])

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["date_only"] = df["date"].dt.date

    current_year = now.year
    current_month = now.month

    # -------------------------------------------------
    # Absence Calculation
    # Morning ✖ = 1 shift
    # Night ✖ = 1 shift
    # 2 shifts = 1 leave day
    # -------------------------------------------------
    df["absent_shifts"] = (
        (df["Morning"] == "✖").astype(int) +
        (df["Night"] == "✖").astype(int)
    )

    df["leave_days"] = df["absent_shifts"] / 2

    # =================================================
    # 1️⃣ Leave Analysis (Month / Year)
    # =================================================
    st.subheader("📊 Leave Analysis (Days)")

    view_type = st.radio(
        "View leave data for:",
        ["Current Month", "Current Year"],
        horizontal=True
    )

    if view_type == "Current Month":
        temp = df[
            (df["year"] == current_year) &
            (df["month"] == current_month)
        ]
        caption = "Leave days taken per employee (Current Month)"
    else:
        temp = df[df["year"] == current_year]
        caption = "Leave days taken per employee (Current Year)"

    leave_df = (
        temp.groupby("Employee Name", as_index=False)["leave_days"]
        .sum()
        .rename(columns={
            "Employee Name": "Employee",
            "leave_days": "Leave Days"
        })
        .sort_values("Leave Days", ascending=False)
        .reset_index(drop=True)
    )

    st.caption(caption)
    st.dataframe(leave_df, use_container_width=True)

    st.markdown("---")

    # =================================================
    # 2️⃣ Shift-wise Absentee Breakdown
    # =================================================
    st.subheader("⏰ Shift-wise Absentee Breakdown")

    shift_df = pd.DataFrame([
        {"Shift": "Morning", "Absent Count": (df["Morning"] == "✖").sum()},
        {"Shift": "Night", "Absent Count": (df["Night"] == "✖").sum()},
    ]).sort_values("Absent Count", ascending=False).reset_index(drop=True)

    st.caption("Total absentees per shift (all time)")
    st.dataframe(shift_df, use_container_width=True)

    st.markdown("---")

    # =================================================
    # 3️⃣ Day-wise Absentees by Shift (CURRENT MONTH ONLY)
    # =================================================
    st.subheader("📋 Day-wise Absentees by Shift (Current Month)")
    
    # Filter to current month ONLY
    month_df = df[
        (df["year"] == current_year) &
        (df["month"] == current_month)
    ]
    
    rows = []
    
    for day, day_df in month_df.groupby("date_only"):
    
        # Morning absentees
        morning_absent = day_df.loc[
            day_df["Morning"] == "✖", "Employee Name"
        ].tolist()
    
        if morning_absent:
            rows.append({
                "Date": day.strftime(DATE_FMT),
                "Shift": "Morning",
                "Absent Count": len(morning_absent),
                "Absent Employees": ", ".join(morning_absent)
            })
    
        # Night absentees
        night_absent = day_df.loc[
            day_df["Night"] == "✖", "Employee Name"
        ].tolist()
    
        if night_absent:
            rows.append({
                "Date": day.strftime(DATE_FMT),
                "Shift": "Night",
                "Absent Count": len(night_absent),
                "Absent Employees": ", ".join(night_absent)
            })
    
    if rows:
        abs_df = (
            pd.DataFrame(rows)
            .sort_values(["Date", "Shift"],ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(abs_df, use_container_width=True)
    else:
        st.info("No absentees recorded for the current month.")


# =================================================
# 📊 SALES ANALYTICS
# =================================================
elif section == "📊 Sales Analytics":

    st.markdown("## 📊 Sales Analytics")

    # =================================================
    # 📥 LOAD SALES DATA
    # =================================================
    records = sales_sheet.get_all_records()
    if not records:
        st.info("No sales data available yet.")
        st.stop()

    df = pd.DataFrame(records)

    # -------------------------------------------------
    # Data Cleaning & Date Normalization
    # -------------------------------------------------
    df["Cash Total"] = pd.to_numeric(df["Cash Total"], errors="coerce")

    df["date"] = pd.to_datetime(
        df["Date"],
        format=DATE_FMT,       # DD/MM/YYYY
        errors="coerce"
    )

    df = df.dropna(subset=["date", "Cash Total"])

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["date_only"] = df["date"].dt.date

    current_year = now.year
    current_month = now.month

    # =================================================
    # 📌 MONTHLY KPI SUMMARY
    # =================================================
    monthly_sales_df = df[
        (df["year"] == current_year) &
        (df["month"] == current_month)
    ]

    monthly_sales = monthly_sales_df["Cash Total"].sum()

    # ---------- Monthly Expenses ----------
    expense_df = pd.DataFrame(expense_sheet.get_all_records())

    if not expense_df.empty:
        expense_df["Expense Amount"] = pd.to_numeric(
            expense_df["Expense Amount"], errors="coerce"
        )

        expense_df["datetime"] = pd.to_datetime(
            expense_df["Date & Time"],
            format=DATETIME_FMT,
            errors="coerce"
        )

        expense_df = expense_df.dropna(subset=["datetime", "Expense Amount"])
        expense_df["year"] = expense_df["datetime"].dt.year
        expense_df["month"] = expense_df["datetime"].dt.month

        monthly_expense = expense_df[
            (expense_df["year"] == current_year) &
            (expense_df["month"] == current_month)
        ]["Expense Amount"].sum()
    else:
        monthly_expense = 0.0

    monthly_profit = monthly_sales - monthly_expense

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Total Sales (This Month)", f"₹ {monthly_sales:,.0f}")
    col2.metric("💸 Total Expenses (This Month)", f"₹ {monthly_expense:,.0f}")
    col3.metric("📈 Profit / Loss (This Month)", f"₹ {monthly_profit:,.0f}")

    st.markdown("---")

    # =================================================
    # 1️⃣ Store-wise Sales (Total / Average Per Day)
    # =================================================
    st.subheader("🏪 Store-wise Sales")

    metric_type = st.radio(
        "View:",
        ["Total", "Average"],
        horizontal=True
    )

    if metric_type == "Total":
        store_df = (
            df.groupby("Store", as_index=False)["Cash Total"]
            .sum()
            .rename(columns={"Cash Total": "Total Sales"})
            .sort_values("Total Sales", ascending=False)
            .reset_index(drop=True)
        )
        st.caption("Store-wise Total Sales")

    else:
        daily_store_sales = (
            df.groupby(["date_only", "Store"], as_index=False)["Cash Total"]
            .sum()
        )

        store_df = (
            daily_store_sales
            .groupby("Store", as_index=False)["Cash Total"]
            .mean()
            .rename(columns={"Cash Total": "Average Daily Sales"})
            .sort_values("Average Daily Sales", ascending=False)
            .reset_index(drop=True)
        )
        st.caption("Store-wise Average Daily Sales")

    st.dataframe(store_df, use_container_width=True)

    st.markdown("---")

    # =================================================
    # 2️⃣ Day-wise Sales (Current Month) + Expense + Profit
    # =================================================
    st.subheader("📅 Day-wise Sales (Current Month)")

    month_df = df[
        (df["year"] == current_year) &
        (df["month"] == current_month)
    ]

    if month_df.empty:
        st.info("No sales data for the current month.")
        st.stop()

    # ---------- Sales per day & store ----------
    day_store_df = (
        month_df
        .groupby(["date_only", "Store"], as_index=False)["Cash Total"]
        .sum()
    )

    # ---------- Total sales per day ----------
    daily_sales = (
        day_store_df
        .groupby("date_only", as_index=False)["Cash Total"]
        .sum()
        .rename(columns={"Cash Total": "Total Sales"})
    )

    # ---------- Expenses per day ----------
    expense_df["date_only"] = expense_df["datetime"].dt.date

    daily_expense = (
        expense_df
        .groupby("date_only", as_index=False)["Expense Amount"]
        .sum()
        .rename(columns={"Expense Amount": "Total Expense"})
    )

    # ---------- Merge ----------
    final_df = (
        day_store_df
        .merge(daily_sales, on="date_only", how="left")
        .merge(daily_expense, on="date_only", how="left")
    )

    final_df["Total Expense"] = final_df["Total Expense"].fillna(0)
    final_df["Profit / Loss"] = final_df["Total Sales"] - final_df["Total Expense"]

    # Show totals only once per date
    for col in ["Total Sales", "Total Expense", "Profit / Loss"]:
        final_df[col] = (
            final_df.groupby("date_only")[col]
            .transform(lambda x: [""] * (len(x) - 1) + [x.iloc[0]])
        )

    final_df["Date"] = final_df["date_only"].apply(
        lambda x: x.strftime(DATE_FMT)
    )

    final_df = final_df[[
        "Date",
        "Store",
        "Cash Total",
        "Total Sales",
        "Total Expense",
        "Profit / Loss"
    ]].sort_values(["Date", "Store"],ascending=False).reset_index(drop=True)

    st.dataframe(final_df, use_container_width=True)
































