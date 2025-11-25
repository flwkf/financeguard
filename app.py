# app.py
import streamlit as st
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import altair as alt
import os
from bson.objectid import ObjectId

# -------------------------
# CONFIG / CONNECT TO MONGO
# -------------------------
# Recommended: set MONGO_URI as Streamlit secret or env var
# e.g. in terminal before run: export MONGO_URI="mongodb+srv://user:pass@cluster0.../dbname?retryWrites=true&w=majority"
MONGO_URI = st.secrets["mongo_uri"] if "mongo_uri" in st.secrets else os.getenv("MONGO_URI")
if not MONGO_URI:
    st.error("MONGO_URI belum diset. Simpan di Streamlit secrets (key: mongo_uri) atau environment variable MONGO_URI.")
    st.stop()

client = MongoClient(MONGO_URI)
db_name = "financeguard"   # bebas, sesuaikan sendiri
db = client[db_name]
sources_col = db["wallet_sources"]
expenses_col = db["expenses"]

# -------------------------
# HELPERS
# -------------------------
def get_sources_list():
    docs = list(sources_col.find().sort("name", 1))
    return docs

def add_source(name):
    if not name.strip():
        return False, "Nama sumber kosong."
    if sources_col.find_one({"name": name.strip()}):
        return False, "Sumber sudah ada."
    sources_col.insert_one({
        "name": name.strip(),
        "created_at": datetime.utcnow()
    })
    return True, "Sumber ditambahkan."

def delete_source(source_id):
    # only delete if no expenses reference OR optionally cascade
    cnt = expenses_col.count_documents({"source_id": ObjectId(source_id)})
    if cnt > 0:
        return False, f"Tidak dapat menghapus: ada {cnt} pengeluaran terkait. Hapus pengeluaran dulu atau pindahkan sumber."
    sources_col.delete_one({"_id": ObjectId(source_id)})
    return True, "Sumber dihapus."

def add_expense(amount, source_id, note, date):
    try:
        amount_val = float(amount)
    except:
        return False, "Nominal tidak valid."
    doc = {
        "amount": amount_val,
        "source_id": ObjectId(source_id),
        "note": note.strip(),
        "date": datetime.combine(date, datetime.min.time()),
        "created_at": datetime.utcnow()
    }
    expenses_col.insert_one(doc)
    return True, "Pengeluaran tercatat."

def delete_expense(expense_id):
    expenses_col.delete_one({"_id": ObjectId(expense_id)})
    return True

def expenses_to_df(filter_source_id=None, start=None, end=None):
    query = {}
    if filter_source_id:
        query["source_id"] = ObjectId(filter_source_id)
    if start:
        query["date"] = query.get("date", {})
        query["date"]["$gte"] = start
    if end:
        query["date"] = query.get("date", {})
        query["date"]["$lte"] = end
    docs = list(expenses_col.find(query).sort("date", -1))
    if not docs:
        return pd.DataFrame(columns=["_id","date","amount","source_id","source_name","note"])
    # load sources map
    sources = {s["_id"]: s["name"] for s in get_sources_list()}
    rows = []
    for d in docs:
        rows.append({
            "_id": str(d["_id"]),
            "date": d.get("date"),
            "amount": d.get("amount", 0.0),
            "source_id": str(d.get("source_id")),
            "source_name": sources.get(d.get("source_id"), "Unknown"),
            "note": d.get("note","")
        })
    df = pd.DataFrame(rows)
    return df

def aggregate_trend(df, period="D"):  # D=day, W=week, M=month
    if df.empty:
        return df
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    if period == "D":
        tmp["period"] = tmp["date"].dt.date
    elif period == "W":
        tmp["period"] = tmp["date"].dt.to_period("W").apply(lambda r: r.start_time.date())
    elif period == "M":
        tmp["period"] = tmp["date"].dt.to_period("M").apply(lambda r: r.start_time.date())
    agg = tmp.groupby("period", as_index=False)["amount"].sum().sort_values("period")
    return agg

# -------------------------
# UI LAYOUT
# -------------------------
st.set_page_config(page_title="Dompet Multi-Sumber", layout="wide")
st.title("Aplikasi Pencatatan Pengeluaran — Multi Sumber")

# Sidebar: manage sources + filter
st.sidebar.header("Sumber Dana")
with st.sidebar.form("add_source_form", clear_on_submit=True):
    new_source_name = st.text_input("Nama sumber (mis. Mandiri, ShopeePay, Cash)", "")
    submitted = st.form_submit_button("Tambah sumber")
    if submitted:
        ok, msg = add_source(new_source_name)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

sources = get_sources_list()
source_options = {str(s["_id"]): s["name"] for s in sources}
st.sidebar.markdown("**Daftar sumber**")
if sources:
    for s in sources:
        cols = st.sidebar.columns([3,1])
        cols[0].markdown(f"- **{s['name']}**")
        if cols[1].button("Hapus", key=f"delsrc_{s['_id']}"):
            ok, msg = delete_source(s["_id"])
            if ok:
                st.success(msg)
                st.experimental_rerun()
            else:
                st.error(msg)
else:
    st.sidebar.write("Belum ada sumber. Tambahkan di atas.")

st.sidebar.markdown("---")
st.sidebar.header("Filter & Impor")
with st.sidebar.form("filter_form"):
    src_filter = st.selectbox("Filter sumber (semua jika kosong)", options=[""] + list(source_options.keys()), format_func=lambda x: "Semua" if x=="" else source_options.get(x, x))
    start_date = st.date_input("Mulai dari", value=None)
    end_date = st.date_input("Sampai", value=None)
    btn_filter = st.form_submit_button("Terapkan filter")
    if btn_filter:
        pass  # values used below

# Main: add expense
st.subheader("Catat Pengeluaran")
cols = st.columns(2)
with cols[0]:
    if not sources:
        st.info("Tambahkan sumber dana di sidebar terlebih dahulu.")
    else:
        with st.form("expense_form", clear_on_submit=True):
            amt = st.number_input("Nominal (Rp)", min_value=0.0, format="%.2f")
            src_choice = st.selectbox("Pilih sumber", options=list(source_options.keys()), format_func=lambda k: source_options.get(k))
            date_choice = st.date_input("Tanggal pengeluaran", value=datetime.today().date())
            note = st.text_input("Catatan (opsional)")
            submit_exp = st.form_submit_button("Simpan pengeluaran")
            if submit_exp:
                ok, msg = add_expense(amt, src_choice, note, date_choice)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

st.markdown("---")
st.subheader("Daftar Pengeluaran")
# get dataframe with filters
df = expenses_to_df(filter_source_id=(src_filter if src_filter!="" else None),
                    start=(pd.to_datetime(start_date) if start_date else None),
                    end=(pd.to_datetime(end_date) if end_date else None))
if df.empty:
    st.write("Belum ada pengeluaran untuk filter ini.")
else:
    # show table and allow deletion
    df_display = df.copy()
    df_display["date"] = pd.to_datetime(df_display["date"]).dt.date
    df_display = df_display[["_id","date","amount","source_name","note"]].rename(columns={
        "_id":"id","date":"Tanggal","amount":"Nominal","source_name":"Sumber","note":"Catatan"
    })
    st.dataframe(df_display.sort_values("Tanggal", ascending=False).reset_index(drop=True), use_container_width=True)

    # deletion
    st.markdown("**Hapus pengeluaran**")
    del_id = st.text_input("Masukkan id pengeluaran untuk dihapus (lihat kolom id)", "")
    if st.button("Hapus pengeluaran"):
        if del_id.strip():
            try:
                delete_expense(del_id.strip())
                st.success("Pengeluaran dihapus.")
                st.experimental_rerun()
            except Exception as e:
                st.error("Gagal menghapus. Pastikan id benar.")
        else:
            st.error("Masukkan id yang valid.")

# -------------------------
# REPORTS / TRENDS
# -------------------------
st.markdown("---")
st.subheader("Laporan Tren")

# choose period and source
report_col1, report_col2 = st.columns([2,1])
with report_col1:
    rep_src = st.selectbox("Pilih sumber untuk laporan", options=["Semua"] + list(source_options.values()))
with report_col2:
    rep_period = st.selectbox("Periode tren", options=["Harian","Mingguan","Bulanan"])

# prepare df for report (ignore deletion id)
# convert df amounts to numeric
df_report = df.copy()
if not df_report.empty:
    df_report["date"] = pd.to_datetime(df_report["date"])
    # if specific source selected
    if rep_src != "Semua":
        df_report = df_report[df_report["source_name"] == rep_src]

# aggregate
if df_report.empty:
    st.info("Tidak ada data untuk membuat laporan (periksa filter/tanggal).")
else:
    period_code = {"Harian":"D","Mingguan":"W","Bulanan":"M"}[rep_period]
    agg = aggregate_trend(df_report, period=period_code)
    if agg.empty:
        st.write("Tidak ada data teragregasi.")
    else:
        # chart with altair
        agg["period"] = pd.to_datetime(agg["period"])
        chart = alt.Chart(agg).mark_line(point=True).encode(
            x=alt.X("period:T", title="Periode"),
            y=alt.Y("amount:Q", title="Total Pengeluaran (Rp)"),
            tooltip=[alt.Tooltip("period:T", title="Periode"), alt.Tooltip("amount:Q", title="Total (Rp)")]
        ).properties(width=800, height=300)
        st.altair_chart(chart, use_container_width=True)
        st.write("Tabel ringkasan:")
        st.dataframe(agg.assign(period=agg["period"].dt.date).rename(columns={"period":"Periode","amount":"Total (Rp)"}))

st.markdown("---")
st.caption("Catatan: gunakan Streamlit secrets (Key: mongo_uri) atau environment variable MONGO_URI untuk menyimpan koneksi ke MongoDB Atlas.")
