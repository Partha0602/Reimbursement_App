# Lunch_Reimbursement.py

import streamlit as st
from st_aggrid import AgGrid
from st_aggrid.grid_options_builder import GridOptionsBuilder
import pandas as pd
from datetime import date, datetime
import os
from dotenv import load_dotenv
import json
from ocr_groq import extract_bill_details_from_image
from db_utils import load_employee_data, load_claim_history, append_claim_record, check_attendance  # ✅ Updated


load_dotenv()

st.title("Lunch Reimbursement Portal")
city = st.radio("Where are you located?", ["Chennai", "Bangalore"])

col1, col2 = st.columns(2)
with col1:
    order_date = st.date_input("Order Date", value=date.today())
with col2:
    claim_date = st.date_input("Claim Date", value=date.today())

if claim_date < order_date:
    st.error("Claim Date cannot be before Order Date.")
    st.stop()
elif (claim_date - order_date).days > 15:
    st.error("You are not eligible as you are claiming after 15 days from the Order Date.")
    st.stop()

employee_df = load_employee_data()
st.write("---")
st.subheader("Claimant Details")

employee_ids = [""] + employee_df["Employee ID"].tolist()
claimant_id = st.selectbox(
    "Enter your Employee ID", 
    employee_ids, 
    index=0, 
    format_func=lambda x: x if x != "" else "Select Employee ID"
)

if claimant_id == "":
    st.stop()

claimant_row = employee_df[employee_df["Employee ID"] == claimant_id].iloc[0]


claimant_info_pairs = [
    ("Name", claimant_row["Employee Name"]),
    ("Designation", claimant_row["Designation"]),
    ("Project", claimant_row["Project"]),
    ("Manager", claimant_row["Reporting Manager"]),
    ("Email", claimant_row["Email"]),
    ("Contact", claimant_row["Contact"])
]

with st.container(height=150):
    for i in range(0, 6, 2):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**{claimant_info_pairs[i][0]}:** {claimant_info_pairs[i][1]}")
        with col2:
            st.markdown(f"**{claimant_info_pairs[i+1][0]}:** {claimant_info_pairs[i+1][1]}")


st.write("---")
# Group selection
st.subheader("Group Members")
employee_options = [
    f"{row['Employee Name']} ({row['Employee ID']})" for _, row in employee_df.iterrows()
]
default_selection = f"{claimant_row['Employee Name']} ({claimant_id})"
selected_members = st.multiselect(
    "Select all group members who were part of this lunch",
    options=employee_options,
    default=[default_selection]
)


group_json = []
selected_ids = set()
absent_employees = []

for display in selected_members:
    emp_id = display.split("(")[-1].strip(")")
    emp_row = employee_df[employee_df["Employee ID"] == emp_id].iloc[0]

    is_present = check_attendance(emp_id, order_date.strftime("%Y-%m-%d"))
    if not is_present:
        absent_employees.append(emp_row["Employee Name"])
    else:
        selected_ids.add(emp_id)
        group_json.append({
            "id": str(emp_id),
            "name": str(emp_row["Employee Name"])
        })

if absent_employees:
    st.error(f"The following employees were absent on {order_date.strftime('%Y-%m-%d')} and are not eligible: {', '.join(absent_employees)}")
    st.stop()

# Duplicate check
st.write(f"Total Members Selected: {len(group_json)}")
already_claimed_names = []
history_df = load_claim_history()

if not history_df.empty:
    for _, row in history_df.iterrows():
        if str(row["Order Date"]).split()[0] == str(order_date):  
            try:
                previous_group = json.loads(row["Group Members"].replace("'", '"'))
                previous_ids = {member["id"] for member in previous_group}
                overlap = selected_ids & previous_ids
                for emp_id in overlap:
                    name = employee_df[employee_df["Employee ID"] == emp_id]["Employee Name"].values[0]
                    already_claimed_names.append(name)
            except Exception:
                pass

if already_claimed_names:
    st.error(f"The following employees already claimed for reimbursement on {order_date}: {', '.join(already_claimed_names)}")
    st.stop()

st.write("---")
# Upload bill
bill_number=st.text_input("Enter Bill Number")
entered_amount = st.number_input("Enter Bill Amount (₹)", min_value=0.0, step=0.01, format="%.2f")
bill_data = None
bill_file_path = ""
bill_data_list = []
temp_df = pd.DataFrame(columns=["filename", "cost", "date", "restaurant"])

if entered_amount > 0:
    st.subheader("Upload Bill(s)")

    num_bills = st.selectbox("Select number of bills to upload", options=list(range(1, 6)), index=0)
    uploaded_files = []

    for i in range(num_bills):
        uploaded_file = st.file_uploader(f"Upload Bill {i+1}", type=None, key=f"bill_{i}")
        if uploaded_file:
            uploaded_files.append(uploaded_file)

    if len(uploaded_files) == num_bills:
        with st.spinner("Extracting bill details using Groq..."):
            for file in uploaded_files:
                save_dir = "data/bills"
                os.makedirs(save_dir, exist_ok=True)
                bill_path = os.path.join(save_dir, file.name)
                with open(bill_path, "wb") as f:
                    f.write(file.getbuffer())

                extracted = extract_bill_details_from_image(file)
                if extracted:
                    extracted_amount = float(extracted.get("total", 0.0))
                    bill_data_list.append(extracted)
                    temp_df = pd.concat([temp_df, pd.DataFrame([{
                        "filename": file.name,
                        "cost": extracted_amount,
                        "date": extracted.get("date", ""),
                        "restaurant": extracted.get("restaurant_name", "N/A")
                    }])], ignore_index=True)
                else:
                    st.error(f"Could not extract data from {file.name}")
                    st.stop()

        agg_bill = temp_df["cost"].sum()
        if abs(entered_amount - agg_bill) < 1.0:
            st.success(f"Bill amounts match! Entered: ₹{entered_amount:.2f}, Extracted Total: ₹{agg_bill:.2f}")
        else:
            st.error(f"Total bill amount mismatch.\n\nEntered: ₹{entered_amount:.2f}, Extracted: ₹{agg_bill:.2f}")
            st.stop()

        # Validate all extracted dates
        for idx, row in temp_df.iterrows():
            date_str = str(row["date"]).strip()
            parsed_date = None

           
            possible_formats = [
                "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
                "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
                "%d/%m/%y", "%m/%d/%y", "%y/%m/%d", "%y-%m-%d"
            ]

            for fmt in possible_formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    if dt.year < 100:
                        dt = dt.replace(year=2000 + dt.year)
                    parsed_date = dt.date()
                    break
                except ValueError:
                    continue

            if parsed_date is None or parsed_date != order_date:
                formatted_order_date = order_date.strftime('%Y/%m/%d')
                formatted_bill_date = parsed_date.strftime('%Y/%m/%d') if parsed_date else date_str
                st.error(f"Bill date mismatch in file {row['filename']}\n\nOrder Date: {formatted_order_date}, Bill Date: {formatted_bill_date}")
                st.stop()

        st.success(f"Bill date matches the entered Order Date ({order_date.strftime('%Y-%m-%d')})")

      
        display_df = temp_df[["restaurant", "date", "cost"]].rename(columns={
            "restaurant": "Restaurant",
            "date": "Date",
            "cost": "Cost"
        })

        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_default_column(editable=False, resizable=True, wrapText=True, autoHeight=True)

        for col in display_df.columns:
            gb.configure_column(col, cellStyle={"textAlign": "left"}, headerClass="ag-left-aligned-header")

        gb.configure_grid_options(domLayout='normal')
        grid_options = gb.build()

        st.subheader("Bill Summary")
        AgGrid(
            display_df,
            gridOptions=grid_options,
            height=100,
            fit_columns_on_grid_load=True,
            enable_enterprise_modules=False
        )

        # Use aggregate data for reimbursement
        bill_data = bill_data_list[0] if bill_data_list else None  
        bill_data["total"] = agg_bill
        bill_file_path = ", ".join([os.path.join("data/bills", f.name) for f in uploaded_files])

    else:
        st.info("Please upload all selected number of bills.")


st.write("---")
# Reimbursement
st.subheader("Reimbursement Calculation")
bill_amount = bill_data.get("total", 0.0) if bill_data else 0.0
num_people = len(group_json)
max_allowed = num_people * 400
reimbursed_amount = min(bill_amount, max_allowed)

st.write(f"Total People: {num_people}")
st.write(f"Maximum Allowable Amount: ₹{max_allowed}")
st.success(f"Reimbursed Amount: ₹{reimbursed_amount:.2f}")
st.write("---")
# Save
st.subheader("Save Claim to History")
order_date_str = order_date.strftime("%Y-%m-%d")
claim_date_str = claim_date.strftime("%Y-%m-%d")

claim_data = {
    "Order Date": order_date_str,
    "Claim Date": claim_date_str,
    "Claimant ID": claimant_id,
    "Group Members": json.dumps(group_json),
    "Bill Amount": bill_amount,
    "Reimbursed Amount": reimbursed_amount,
    "Bill Number": bill_number,
    "Bill File": bill_file_path
}

if  bill_data and bill_data.get("total", 0.0) > 0 and group_json:
    if st.button("Submit Claim"):
        claim_data["Status"] = "Pending"
        append_claim_record(claim_data)
        st.success("Claim submitted and recorded successfully!")
        st.info("Request Pending")
else:
    st.info("Please ensure all fields are filled, bill is uploaded and valid, and group members are selected to submit.")
