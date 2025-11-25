import streamlit as st
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import pandas as pd
import altair as alt
import os

# ===============================
# KONFIGURASI MONGO ATLAS
# ===============================
MONGO_URI = st.secrets["MONGO_URI"]  # pastikan kamu isi di .streamlit/secrets.toml
client = MongoClient(MONGO_URI)

# Jika URI tidak punya default DB → fallback
try:
    db = client.get_default_database()
except:
    db = client["financeguard"]

sources_col = db["wallet_sources"]
expenses_col = db["expenses"]

st.title("📒 Aplikasi Pencatatan Dompet & Pengeluaran")


# ===============================
# AMBIL DATA SUMBER DANA
# ===============================
def load_sources():
    src_list = list(sources_col.find())
    return {str(s["_id"]): s["name"] for s in src_list}

source_options = load_sources()


# ===============================
# TAMBAH SUMBER DOMPET
# ===============================
st.subheader("Tambah Sumber Dompet")
with st.form("add_source_form", clear_on_submit=True):
    new_source = st.text_input("Nama sumber (contoh: Mandiri, ShopeePay, Cash)")
    add_src = st.form_submit_button("Tambah Sumber")

    if add_src:
        if new_source.strip() == "":
            st.error("Nama sumber tidak boleh kosong.")
        else:
            sources_col.insert_one({"name": new_source})
            st.success("Sumber berhasil ditambahkan!")
            st.experimental_rerun()


# ===============================
# FUNGSI: TAMBAH PENGELUARAN
# ===============================
def add_expense(amount, source_id, note, date):
    try:
        amount_val = float(amount)
    except:
        return False, "Nominal tidak valid."

    doc = {
        "amount": amount_val,
        "source_id": ObjectId(source_id),
        "note": note,
        "date": datetime.combine(date, datetime.min.time()),
        "type": "expense",
        "created_at": datetime.utcnow(),
    }
    expenses_col.insert_one(doc)
    return True, "Pengeluaran berhasil dicatat."


# ===============================
# FORM PENGELUARAN
# ===============================
st.subheader("Catat Pengeluaran")

if len(source_options) == 0:
    st.warning("Tambahkan sumber dompet terlebih dahulu.")
else:
    with st.form("expense_form", clear_on_submit=True):
        ex_amount = st.number_input("Nominal", min_value=0.0, format="%.2f")
        ex_source = st.selectbox("Sumber Dana", options=list(source_options.keys()), format_func=lambda k: source_options[k])
        ex_date = st.date_input("Tanggal", value=datetime.today().date())
        ex_note = st.text_input("Catatan")
        ex_submit = st.form_submit_button("Catat")

        if ex_submit:
            ok, msg = add_expense(ex_amount, ex_source, ex_note, ex_date)
            if ok:
                st.success(msg)
            else:
                st.error(msg)


# ===============================
# FUNGSI: TRANSFER ANTAR DOMPET
# ===============================
def add_transfer(amount, source_from, source_to, note, date):
    amount_val = float(amount)
    dt = datetime.combine(date, datetime.min.time())

    # transaksi keluar
    expenses_col.insert_one({
        "amount": amount_val,
        "source_id": ObjectId(source_from),
        "note": f"Transfer ke {source_options[source_to]} - {note}",
        "date": dt,
        "type": "transfer_out",
        "created_at": datetime.utcnow()
    })

    # transaksi masuk
    expenses_col.insert_one({
        "amount": amount_val,
        "source_id": ObjectId(source_to),
        "note": f"Transfer dari {source_options[source_from]} - {note}",
        "date": dt,
        "type": "transfer_in",
        "created_at": datetime.utcnow()
    })

    return True, "Transfer berhasil."


# ===============================
# FORM TRANSFER
# ===============================
st.subheader("Transfer Antar Dompet")

if len(source_options) < 2:
    st.info("Tambahkan minimal 2 dompet untuk dapat transfer.")
else:
    with st.form("transfer_form", clear_on_submit=True):
        tf_amount = st.number_input("Nominal Transfer", min_value=0.0, format="%.2f")
        col1, col2 = st.columns(2)
        with col1:
            tf_from = st.selectbox("Dari", options=list(source_options.keys()), format_func=lambda k: source_options[k])
        with col2:
            tf_to = st.selectbox("Ke", options=list(source_options.keys()), format_func=lambda k: source_options[k])

        tf_date = st.date_input("Tanggal Transfer", value=datetime.today().date())
        tf_note = st.text_input("Catatan (opsional)")
        tf_submit = st.form_submit_button("Catat Transfer")

        if tf_submit:
            if tf_from == tf_to:
                st.error("Dompet asal dan tujuan tidak boleh sama.")
            else:
                ok, msg = add_transfer(tf_amount, tf_from, tf_to, tf_note, tf_date)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


# ===============================
# LOAD DATA RIWAYAT
# ===============================
st.subheader("Riwayat Transaksi")

data = list(expenses_col.find().sort("date", -1))

if not data:
    st.info("Belum ada transaksi.")
else:
    df = pd.DataFrame(data)
    df["id"] = df["_id"].astype(str)
    df["source"] = df["source_id"].astype(str).map(source_options)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    show_df = df[["date", "amount", "source", "note", "type"]]
    st.dataframe(show_df)


# ===============================
# HITUNG SALDO TIAP DOMPET
# ===============================
st.subheader("Ringkasan Saldo Tiap Dompet")

saldo = {}
for sid, name in source_options.items():
    df_src = df[df["source_id"].astype(str) == sid]

    total_in = df_src[df_src["type"].isin(["transfer_in"])]["amount"].sum()
    total_out = df_src[df_src["type"].isin(["transfer_out", "expense"])]["amount"].sum()

    saldo[name] = total_in - total_out

saldo_df = pd.DataFrame({
    "Dompet": saldo.keys(),
    "Saldo": saldo.values()
})

st.table(saldo_df)


# ===============================
# GRAFIK TREN HARIAN / MINGGUAN / BULANAN
# ===============================
st.subheader("Laporan Tren Pengeluaran")

df_exp = df[df["type"] == "expense"].copy()
df_exp["date"] = pd.to_datetime(df_exp["date"])

period = st.selectbox("Pilih periode", ["Harian", "Mingguan", "Bulanan"])

if period == "Harian":
    g = df_exp.groupby("date")["amount"].sum().reset_index()
elif period == "Mingguan":
    df_exp["week"] = df_exp["date"].dt.to_period("W").astype(str)
    g = df_exp.groupby("week")["amount"].sum().reset_index()
    g.rename(columns={"week": "date"}, inplace=True)
else:
    df_exp["month"] = df_exp["date"].dt.to_period("M").astype(str)
    g = df_exp.groupby("month")["amount"].sum().reset_index()
    g.rename(columns={"month": "date"}, inplace=True)

chart = (
    alt.Chart(g)
    .mark_line(point=True)
    .encode(
        x="date:T",
        y="amount:Q"
    )
)

st.altair_chart(chart, use_container_width=True)
