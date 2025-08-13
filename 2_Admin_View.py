# admin_view_page.py
import streamlit as st
import pandas as pd
import json
import os
import base64
import imghdr
import time
from dotenv import load_dotenv
from st_aggrid import AgGrid, JsCode
from st_aggrid.grid_options_builder import GridOptionsBuilder
from st_aggrid import GridUpdateMode
from db_utils import engine, update_claim_status  



st.title("Admin View")

load_dotenv()


try:
    query = "SELECT * FROM ClaimHistory"
    df = pd.read_sql(query, engine)
    df = df.sort_values(by="Claim Date", ascending=False)
    
    # format date columns if present
    if not df.empty:
        for date_col in ["Order Date", "Claim Date"]:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

    if df.empty:
        st.info("No claims have been submitted yet.")

    if not df.empty:
        def format_json_column(value):
            try:
                parsed = json.loads(value)
                return json.dumps(parsed, indent=2)
            except:
                return value

        for col in df.columns:
            try:
                if col == "Group Members":
                    def format_group_members(val):
                        try:
                            members = json.loads(val)
                            return ", ".join(f"{m['name']} ({m['id']})" for m in members)
                        except:
                            return val
                    df[col] = df[col].apply(format_group_members)
                elif df[col].astype(str).str.startswith("[{").any():
                    df[col] = df[col].apply(format_json_column)
            except Exception:
                pass


        # prepare base64 image data (do not show original Bill File path later)
        if "Bill File" in df.columns:
            def make_data_uri_or_empty(path_str):
                try:
                    image_tags = []
                    if not path_str or path_str.strip().upper() in ("N/A", "NONE", ""):
                        return ""

                    paths = [p.strip().replace("\\", "/") for p in path_str.split(",")]

                    for p in paths:
                        full_path = os.path.join(os.getcwd(), p) if not os.path.isabs(p) else p
                        if os.path.exists(full_path):
                            with open(full_path, "rb") as f:
                                data = f.read()
                            kind = imghdr.what(None, h=data) or "jpeg"
                            b64 = base64.b64encode(data).decode("utf-8")
                            uri = f"data:image/{kind};base64,{b64}"
                            image_tags.append(uri)

                    # Join multiple base64 URIs with pipe `|` separator
                    return "|".join(image_tags)
                except Exception:
                    return ""


            df["Bill_File_DataURI"] = df["Bill File"].astype(str).apply(make_data_uri_or_empty)
        else:
            df["Bill_File_DataURI"] = ""

        display_df = df.copy()

        # create boolean Approve / Reject columns
        if "Status" in display_df.columns:
            display_df["Approve"] = display_df["Status"].astype(str).str.lower().eq("approved")
            display_df["Reject"] = display_df["Status"].astype(str).str.lower().eq("rejected")
        else:
            display_df["Approve"] = False
            display_df["Reject"] = False

        if "Status" in display_df.columns:
            display_df = display_df.drop(columns=["Status"])

        if "Bill File" in display_df.columns:
            display_df = display_df.drop(columns=["Bill File"])
        display_df = display_df.rename(columns={"Bill_File_DataURI": "Bill Image"})

        orig_cols = list(df.columns)
        status_index = orig_cols.index("Status") if "Status" in orig_cols else None
        if "Bill Image" in display_df.columns and status_index is not None:
            cols = list(display_df.columns)
            cols.remove("Bill Image")
            insert_idx = min(status_index, len(cols))
            cols.insert(insert_idx, "Bill Image")
            display_df = display_df[cols]

        cols = list(display_df.columns)
        for _col in ["Approve", "Reject"]:
            if _col in cols:
                cols.remove(_col)
                cols.append(_col)
        display_df = display_df[cols]

        # JS renderer: image thumbnail
        render_image_modal = JsCode("""
        class ImgCellRenderer {
            init(params) {
                this.params = params;
                const allURIs = (params.value || '').split('|').filter(x => x);
                const span = document.createElement('span');

                if (!allURIs.length) {
                    span.textContent = 'No Image';
                    this.eGui = span;
                    return;
                }

                const modal = document.createElement('div');
                modal.style.position = 'fixed';
                modal.style.top = '0';
                modal.style.left = '0';
                modal.style.width = '100%';
                modal.style.height = '100%';
                modal.style.backgroundColor = 'rgba(0,0,0,0.7)';
                modal.style.display = 'none';
                modal.style.alignItems = 'center';
                modal.style.justifyContent = 'center';
                modal.style.zIndex = '9999';
                modal.style.flexDirection = 'column';

                const modalImg = document.createElement('img');
                modalImg.style.maxHeight = '80%';
                modalImg.style.maxWidth = '80%';
                modalImg.style.borderRadius = '10px';
                modalImg.style.transition = 'transform 0.3s ease';
                modalImg.style.cursor = 'zoom-in';

                const closeBtn = document.createElement('div');
                closeBtn.textContent = '✖';
                closeBtn.style.position = 'absolute';
                closeBtn.style.top = '10px';
                closeBtn.style.right = '20px';
                closeBtn.style.fontSize = '24px';
                closeBtn.style.cursor = 'pointer';
                closeBtn.style.color = 'black';
                closeBtn.style.textDecoration = 'none';
                closeBtn.style.background = 'none';

                closeBtn.onclick = () => {
                    modal.style.display = 'none';
                    modalImg.style.transform = 'scale(1)';
                    modalImg.style.cursor = 'zoom-in';
                };

                let zoomedIn = false;
                modalImg.onclick = (e) => {
                    e.stopPropagation();
                    zoomedIn = !zoomedIn;
                    if (zoomedIn) {
                        modalImg.style.transformOrigin = `${e.offsetX}px ${e.offsetY}px`;
                        modalImg.style.transform = 'scale(2.5)';
                        modalImg.style.cursor = 'zoom-out';
                    } else {
                        modalImg.style.transform = 'scale(1)';
                        modalImg.style.cursor = 'zoom-in';
                    }
                };

                const leftBtn = document.createElement('div');
                leftBtn.textContent = '<';
                leftBtn.style.position = 'absolute';
                leftBtn.style.left = '30px';
                leftBtn.style.top = '50%';
                leftBtn.style.transform = 'translateY(-50%)';
                leftBtn.style.fontSize = '36px';
                leftBtn.style.cursor = 'pointer';
                leftBtn.style.userSelect = 'none';
                leftBtn.style.display = 'none';
                leftBtn.style.color = 'black';
                leftBtn.style.textDecoration = 'none';
                leftBtn.style.background = 'none';

                const rightBtn = document.createElement('div');
                rightBtn.textContent = '>';
                rightBtn.style.position = 'absolute';
                rightBtn.style.right = '30px';
                rightBtn.style.top = '50%';
                rightBtn.style.transform = 'translateY(-50%)';
                rightBtn.style.fontSize = '36px';
                rightBtn.style.cursor = 'pointer';
                rightBtn.style.userSelect = 'none';
                rightBtn.style.display = 'none';
                rightBtn.style.color = 'black';
                rightBtn.style.textDecoration = 'none';
                rightBtn.style.background = 'none';

                let currentIndex = 0;

                const updateImage = () => {
                    modalImg.src = allURIs[currentIndex];
                    zoomedIn = false;
                    modalImg.style.transform = 'scale(1)';
                    modalImg.style.cursor = 'zoom-in';
                    leftBtn.style.display = currentIndex > 0 ? 'block' : 'none';
                    rightBtn.style.display = currentIndex < allURIs.length - 1 ? 'block' : 'none';
                };

                leftBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (currentIndex > 0) {
                        currentIndex--;
                        updateImage();
                    }
                };

                rightBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (currentIndex < allURIs.length - 1) {
                        currentIndex++;
                        updateImage();
                    }
                };

                modal.appendChild(modalImg);
                modal.appendChild(closeBtn);
                modal.appendChild(leftBtn);
                modal.appendChild(rightBtn);
                document.body.appendChild(modal);

                allURIs.forEach((uri, index) => {
                    const thumb = document.createElement('img');
                    thumb.src = uri;
                    thumb.style.height = '80px';
                    thumb.style.marginRight = '5px';
                    thumb.style.cursor = 'zoom-in';
                    thumb.style.borderRadius = '5px';
                    thumb.style.transition = '0.3s';

                    thumb.ondblclick = () => {
                        currentIndex = index;
                        updateImage();
                        modal.style.display = 'flex';
                    };

                    span.appendChild(thumb);
                });

                this.eGui = span;
            }

            getGui() {
                return this.eGui;
            }
        }
    """)

        mutually_exclusive_js = JsCode("""
        function(params) {
        try {
            const fld = params.colDef.field;
            if (fld === 'Approve' && params.newValue === true) {
            params.node.setDataValue('Reject', false);
            }
            if (fld === 'Reject' && params.newValue === true) {
            params.node.setDataValue('Approve', false);
            }
        } catch(e) {}
        }
        """)

        
        row_coloring_js = JsCode("""
        function(params) {
            if (params.data && params.data.Approve === true) {
                return { 'background-color': '#d4edda' };
            }
            if (params.data && params.data.Reject === true) {
                return { 'background-color': '#e28c91' };
            }
            return {};
        }
        """)

        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_pagination()
        gb.configure_default_column(resizable=True, wrapText=True, autoHeight=True)
        gb.configure_grid_options(onCellValueChanged=mutually_exclusive_js)
        gb.configure_grid_options(getRowStyle=row_coloring_js)

        
        gb.configure_column("Bill Image", cellRenderer=render_image_modal, autoHeight=True, width=100)
        gb.configure_column("Approve", editable=True, cellRenderer='agCheckboxCellRenderer', width=90)
        gb.configure_column("Reject", editable=True, cellRenderer='agCheckboxCellRenderer', width=90)

        grid_options = gb.build()
        grid_response = AgGrid(
            display_df,
            gridOptions=grid_options,
            fit_columns_on_grid_load=False,
            enable_enterprise_modules=False,
            allow_unsafe_jscode=True,
            update_mode=GridUpdateMode.VALUE_CHANGED
        )

        if st.button("Apply Status"):
            updated = pd.DataFrame(grid_response.get("data", []))
            conflicting = []
            applied = 0
            errors = []

            for _, row in updated.iterrows():
                bill_number = row.get("Bill Number")
                if not bill_number or str(bill_number).strip() == "":
                    continue

                approve = bool(row.get("Approve", False))
                reject = bool(row.get("Reject", False))

                if approve and reject:
                    conflicting.append(str(bill_number))
                    continue

                if approve:
                    new_status = "Approved"
                elif reject:
                    new_status = "Rejected"
                else:
                    new_status = "Pending"

                try:
                    update_claim_status(str(bill_number), new_status)
                    applied += 1
                except Exception as e:
                    errors.append((bill_number, str(e)))

            if conflicting:
                st.warning(f"Skipping rows (both Approve+Reject checked): {', '.join(conflicting)}")
            if errors:
                st.error(f"Errors updating rows: {errors}")
            st.success(f"Applied updates.")

            try:
                if hasattr(st, "experimental_rerun"):
                    st.experimental_rerun()
                else:
                    st.query_params = {"_refresh": str(time.time())}
            except Exception:
                st.info("Please refresh the page to see updated statuses.")

except Exception as e:
    st.error(f"⚠️ Failed to load claim data from SQL Server.\n\n{e}")



