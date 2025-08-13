# ocr_groq.py

from groq import Groq
import base64
from tempfile import NamedTemporaryFile
import os
import json
import pyodbc
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# SQL Server connection string
conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.getenv('SQL_SERVER')};"
    f"DATABASE={os.getenv('SQL_DATABASE')};"
    f"Trusted_Connection=yes;"
)

def insert_ocr_result_to_sql(data):
    try:
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO OcrExtractedBills (restaurant_name, bill_number, date, total)
                VALUES (?, ?, ?, ?)
            """, (
                data.get("restaurant_name"),
                data.get("bill_number"),
                data.get("date"),
                data.get("total")
            ))
            conn.commit()
    except Exception as e:
        print("SQL insert error:", e)

def extract_bill_details_from_image(uploaded_file):
    try:
        # ✅ Save uploaded file to a temporary location
        file_bytes = uploaded_file.getvalue()  # Ensures full content
        with NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[-1]) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        # ✅ Encode image to base64
        base64_image = base64.b64encode(file_bytes).decode("utf-8")

        # ✅ Send image + instruction to Groq
        result = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract the following details from this restaurant bill image and return ONLY JSON:\n"
                                "{\n"
                                '  "restaurant_name": string,\n'
                                '  "bill_number": string or null,\n'
                                '  "date": "DD/MM/YY" or null,\n'
                                '  "total": float or null\n'
                                "}\n"
                                "Return only JSON. No explanation."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        },
                    ],
                }
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
        )

        response_text = result.choices[0].message.content.strip()

        try:
            extracted_data = json.loads(response_text)
            insert_ocr_result_to_sql(extracted_data)
            return extracted_data
        except json.JSONDecodeError:
            print("Warning: Invalid JSON from OCR. Raw content returned.")
            print(response_text)
            return None

    except Exception as e:
        print("OCR error:", e)
        return None
