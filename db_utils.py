# db_utils.py

import pandas as pd
import pyodbc
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine


load_dotenv()

# SQLAlchemy engine for use with pandas.read_sql
DB_SERVER = os.getenv("SQL_SERVER")
DB_NAME = os.getenv("SQL_DATABASE")
engine = create_engine(
    f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)

def get_connection():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)

def load_employee_data():
    df = pd.read_sql("SELECT * FROM EmployeeMaster", engine)
    return df

def load_claim_history():
    df = pd.read_sql("SELECT * FROM ClaimHistory", engine)
    return df

def check_attendance(emp_id: str, date_str: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT [Status] FROM Attendance
        WHERE [Employee ID] = ? AND [Date] = ?
    """
    cursor.execute(query, (emp_id, date_str))
    row = cursor.fetchone()
    conn.close()
    return row is not None and row.Status.lower() == "present"

def update_claim_status(bill_number: str, new_status: str):
    """
    Update the Status column in ClaimHistory for the given Bill Number.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sql = "UPDATE ClaimHistory SET [Status] = ? WHERE [Bill Number] = ?"
        cursor.execute(sql, (new_status, bill_number))
        conn.commit()
    finally:
        conn.close()

    
def append_claim_record(claim_data):
    conn = get_connection()
    cursor = conn.cursor()
    sql = """
        INSERT INTO ClaimHistory (
            [Order Date], [Claim Date], [Claimant ID], [Group Members],
            [Bill Amount], [Reimbursed Amount], [Bill Number], [Bill File], [Status]
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor.execute(sql, (
        claim_data["Order Date"],
        claim_data["Claim Date"],
        claim_data["Claimant ID"],
        claim_data["Group Members"],
        claim_data["Bill Amount"],
        claim_data["Reimbursed Amount"],
        claim_data["Bill Number"],
        claim_data["Bill File"],
        claim_data["Status"]
    ))
    conn.commit()
    conn.close()
