import streamlit as st
from pymongo import MongoClient
import pandas as pd
from bson.objectid import ObjectId
from datetime import datetime
import altair as alt
import matplotlib.pyplot as plt

st.set_page_config(page_title="Dompet Manager", layout="wide")

# ================================
# KONEKSI MONGO
# ================================
MONGO_URI = st.secrets["MONGO_URI"]
client = MongoClient(MONGO_URI)
db = client["keuangan_app"]
sources_col = db["sources"]
transactions_col = db["transactions"]

st.title("📒 Aplikasi Pengelolaan Dompet & Pengeluaran")


# ================================
# FUNGSI MEMUAT DOMPET
# ================================
def load_sources():
    data = list(sources_col.find())
    return {str(d["_id"]): d["name"] for d in data}


# ================================
# BAGIAN 1: TAMBAH DOMPET
# ================================
st.subheader("➕ Tambah Dompet Baru")

with st.form("add_wallet"):
    nama_dompet = st.text_input("Nama Dompet (contoh: Mandiri, ShopeePay, Cash)")
    submit_dompet = st.form_submit_button("Tambah")

if submit_dompet and nama_dompet.strip():
    sources_col.insert_one({"name": nama_dompet})
    st.success(f"Dompet '{nama_dompet}' berhasil ditambahkan!")


# ================================
# REFRESH DOMPET
# ================================
source_options = load_sources()

# ================================
# BAGIAN: INPUT PEMASUKAN
# ================================
st.subheader("💰 Catat Pemasukan")

with st.form("income_form"):
    source_inc = st.selectbox(
        "Pilih Dompet Tujuan",
        list(source_options.keys()),
        format_func=lambda x: source_options[x]
    )
    amount_inc = st.number_input("Nominal Pemasukan", min_value=0.0)
    desc_inc = st.text_input("Deskripsi Pemasukan")
    submit_inc = st.form_submit_button("Catat Pemasukan")

if submit_inc and amount_inc > 0:
    transactions_col.insert_one({
        "type": "income",
        "source_id": source_inc,
        "amount": amount_inc,
        "description": desc_inc,
        "created_at": datetime.now()
    })
    st.success("Pemasukan berhasil dicatat!")

# ================================
# BAGIAN 2: INPUT PENGELUARAN
# ================================
st.subheader("💸 Catat Pengeluaran")

with st.form("expense_form"):
    source_exp = st.selectbox("Pilih Sumber Dana", list(source_options.keys()),
                              format_func=lambda x: source_options[x])
    amount_exp = st.number_input("Nominal Pengeluaran", min_value=0.0)
    desc_exp = st.text_input("Deskripsi")
    submit_exp = st.form_submit_button("Catat Pengeluaran")

if submit_exp and amount_exp > 0:
    transactions_col.insert_one({
        "type": "expense",
        "source_id": source_exp,
        "amount": amount_exp,
        "description": desc_exp,
        "created_at": datetime.now()
    })
    st.success("Pengeluaran berhasil dicatat!")


# ================================
# BAGIAN 3: TRANSFER ANTAR DOMPET
# ================================
st.subheader("🔁 Transfer Antar Dompet")

with st.form("transfer_form"):
    from_src = st.selectbox("Dari Dompet", list(source_options.keys()),
                            format_func=lambda x: source_options[x])
    to_src = st.selectbox("Ke Dompet", list(source_options.keys()),
                          format_func=lambda x: source_options[x])
    amount_trf = st.number_input("Nominal Transfer", min_value=0.0)
    desc_trf = st.text_input("Deskripsi Transfer")

    submit_trf = st.form_submit_button("Transfer")

if submit_trf and amount_trf > 0 and from_src != to_src:

    # catat keluar dari dompet asal
    transactions_col.insert_one({
        "type": "transfer_out",
        "source_id": from_src,
        "target_id": to_src,
        "amount": amount_trf,
        "description": desc_trf,
        "created_at": datetime.now()
    })

    # catat masuk ke dompet tujuan
    transactions_col.insert_one({
        "type": "transfer_in",
        "source_id": from_src,
        "target_id": to_src,
        "amount": amount_trf,
        "description": desc_trf,
        "created_at": datetime.now()
    })

    st.success("Transfer berhasil dicatat!")


# ================================
# LOAD TRANSAKSI
# ================================
transactions = list(transactions_col.find({}, sort=[("created_at", -1)]))

if len(transactions) > 0:
    df = pd.DataFrame(transactions)
    df["created_at"] = pd.to_datetime(df["created_at"])
else:
    df = pd.DataFrame(columns=[
        "type", "source_id", "target_id", "description",
        "amount", "created_at"
    ])


# ================================
# BAGIAN 4: LAPORAN TREN
# ================================
st.subheader("📊 Laporan Pengeluaran")

if len(df) == 0:
    st.info("Belum ada transaksi.")
else:
    df_exp = df[df["type"] == "expense"]

    if len(df_exp) > 0:
        df_exp["date"] = df_exp["created_at"].dt.date
        df_daily = df_exp.groupby("date")["amount"].sum().reset_index()

        st.markdown("### Tren Harian")
        st.line_chart(df_daily, x="date", y="amount")

        df_exp["week"] = df_exp["created_at"].dt.isocalendar().week
        df_week = df_exp.groupby("week")["amount"].sum().reset_index()

        st.markdown("### Tren Mingguan")
        st.bar_chart(df_week, x="week", y="amount")

        df_exp["month"] = df_exp["created_at"].dt.to_period("M").astype(str)
        df_month = df_exp.groupby("month")["amount"].sum().reset_index()

        st.markdown("### Tren Bulanan")
        st.area_chart(df_month, x="month", y="amount")
    else:
        st.info("Belum ada pengeluaran.")


# ================================
# BAGIAN 5: SALDO DOMPET
# ================================
st.subheader("💰 Saldo Setiap Dompet")

# Pastikan kolom yang mungkin hilang tetap ada
for col in ["source_id", "target_id", "type", "amount"]:
    if col not in df.columns:
        df[col] = None

saldo = {}

for sid, name in source_options.items():

    # ambil transaksi yang sumbernya dompet ini
    df_out = df[df["source_id"].astype(str) == sid]

    # ambil transaksi yang masuk ke dompet ini
    df_in = df[df["target_id"].astype(str) == sid]

    # hitung pemasukan
    total_income = df_out[df_out["type"] == "income"]["amount"].sum()

    # transfer masuk
    total_transfer_in = df_in[df_in["type"] == "transfer_in"]["amount"].sum()

    # pengeluaran
    total_expense = df_out[df_out["type"] == "expense"]["amount"].sum()

    # transfer keluar
    total_transfer_out = df_out[df_out["type"] == "transfer_out"]["amount"].sum()

    # rumus saldo akhir
    saldo[name] = (total_income + total_transfer_in) - (total_expense + total_transfer_out)


# tampilkan tabel saldo rapi
saldo_df = pd.DataFrame([
    {"Dompet": name, "Saldo": amount}
    for name, amount in saldo.items()
])

st.dataframe(
    saldo_df.style.format({"Saldo": "{:,.0f}"}).background_gradient(subset=["Saldo"], cmap="Greens")
)




# ================================
# BAGIAN 6: RIWAYAT TRANSAKSI
# ================================
st.subheader("📚 Riwayat Transaksi")

if len(df) > 0:
    show_df = df.copy()
    show_df["_id"] = show_df["_id"].astype(str)
    show_df["source"] = show_df["source_id"].astype(str).map(source_options)
    show_df["target"] = show_df["target_id"].astype(str).map(source_options)

    st.dataframe(show_df[[
        "_id", "created_at", "type", "source", "target", "description", "amount"
    ]])

    st.markdown("### ✏️ Edit atau ❌ Hapus Transaksi")

    all_ids = list(show_df["_id"])
    selected_id = st.selectbox("Pilih Transaksi", all_ids)

    selected_row = show_df[show_df["_id"] == selected_id].iloc[0]

    with st.form("edit_delete_form"):
        new_type = st.selectbox(
            "Jenis Transaksi",
            ["income", "expense", "transfer_in", "transfer_out"],
            index=["income", "expense", "transfer_in", "transfer_out"].index(selected_row["type"])
        )

        new_source = st.selectbox(
            "Dompet Sumber",
            list(source_options.keys()),
            index=list(source_options.keys()).index(str(selected_row["source_id"]))
        )

        new_target = st.selectbox(
            "Dompet Tujuan (Khusus Transfer)",
            [""] + list(source_options.keys()),
            index=(1 + list(source_options.keys()).index(str(selected_row["target_id"])))
            if pd.notna(selected_row["target_id"]) else 0
        )

        new_desc = st.text_input("Deskripsi", selected_row["description"])
        new_amount = st.number_input("Nominal", min_value=0.0, value=float(selected_row["amount"]))

        col1, col2 = st.columns(2)
        edit_btn = col1.form_submit_button("Simpan Perubahan")
        del_btn = col2.form_submit_button("Hapus Transaksi")

    # ---- ACTION: EDIT ----
    if edit_btn:
        update_data = {
            "type": new_type,
            "source_id": new_source,
            "description": new_desc,
            "amount": new_amount,
        }

        if new_target != "":
            update_data["target_id"] = new_target
        else:
            update_data["target_id"] = None

        transactions_col.update_one(
            {"_id": ObjectId(selected_id)},
            {"$set": update_data}
        )
        st.success("Transaksi berhasil diperbarui!")
        st.rerun()

    # ---- ACTION: DELETE ----
    if del_btn:
        transactions_col.delete_one({"_id": ObjectId(selected_id)})
        st.warning("Transaksi berhasil dihapus!")
        st.rerun()

else:
    st.info("Belum ada transaksi.")
