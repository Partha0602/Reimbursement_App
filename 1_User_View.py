import streamlit as st
import pandas as pd
import json
from sqlalchemy import text
from datetime import datetime
from db_utils import engine  


st.title("My Lunch Claims")


with st.form("search_form"):
    emp_id = st.text_input("Enter your Employee ID", max_chars=10)
    order_date = st.date_input("Select the Order Date")
    submitted = st.form_submit_button("Search")

if submitted:
    if not emp_id.strip():
        st.warning("Please enter a valid Employee ID.")
    else:
        try:
            order_date_str = order_date.strftime("%Y-%m-%d")

            query = text("""
            SELECT [Group Members], [Bill Amount], [Reimbursed Amount], [Status]
            FROM ClaimHistory
            WHERE [Claimant ID] = :emp_id AND CAST([Order Date] AS DATE) = :order_date
            """)
            df = pd.read_sql(query, engine, params={"emp_id": emp_id.strip(), "order_date": order_date_str})

            if df.empty:
                st.info("No claims found for the given Employee ID and Order Date.")
            else:
                if "Group Members" in df.columns:
                    def format_group(val):
                        try:
                            members = json.loads(val)
                            return "\n".join(f"{m['name']} ({m['id']})" for m in members)
                        except:
                            return val
                    df["Group Members"] = df["Group Members"].apply(format_group)

                
                df = df.rename(columns={
                    "Group Members": "Group Members",
                    "Bill Amount": "Bill Amount (₹)",
                    "Reimbursed Amount": "Reimbursed (₹)",
                    "Status": "Current Status"
                })

                
                st.subheader("Claim Details")
                st.dataframe(df, use_container_width=True)

        except Exception as e:
            st.error(f"Error fetching data: {e}")
