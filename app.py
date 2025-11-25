import streamlit as st
from pymongo import MongoClient
import pandas as pd
import datetime

# ---------------------------
# MONGODB CONNECTION
# ---------------------------
client = MongoClient(st.secrets["mongo"]["uri"])
db = client["finance"]
wallets_col = db["wallets"]
trx_col = db["transactions"]

st.set_page_config(page_title="FinanceGuard", layout="wide")

# ---------------------------
# LOAD DATA INTO DATAFRAME
# ---------------------------
def load_wallets():
    data = list(wallets_col.find())
    return {str(d["_id"]): d["name"] for d in data}

def load_transactions():
    data = list(trx_col.find())
    if len(data) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["_id"] = df["_id"].astype(str)
    return df


# =====================================================================
#                           TAB NAVIGATION
# =====================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Dashboard", "➕ Tambah Dompet", "💸 Transaksi", "📜 Riwayat", "📈 Laporan"]
)


# =====================================================================
#                               1. DASHBOARD
# =====================================================================
with tab1:
    st.title("📊 Dashboard Keuangan")

    wallets = load_wallets()
    df = load_transactions()

    # Jika belum ada transaksi, buat df kosong
    if df.empty:
        df["source_id"] = ""
        df["target_id"] = ""
        df["amount"] = 0
        df["type"] = ""

    summary = []

    for wid, name in wallets.items():
        # Uang keluar dan masuk
        df_out = df[df["source_id"].astype(str) == wid]
        df_in = df[df["target_id"].astype(str) == wid]

        income = df[df["type"] == "income"]
        income = income[income["source_id"].astype(str) == wid]["amount"].sum()

        expense = df[df["type"] == "expense"]
        expense = expense[expense["source_id"].astype(str) == wid]["amount"].sum()

        transfer_in = df_in[df_in["type"] == "transfer_in"]["amount"].sum()
        transfer_out = df_out[df_out["type"] == "transfer_out"]["amount"].sum()

        saldo = (income + transfer_in) - (expense + transfer_out)

        summary.append({"Dompet": name, "Saldo": saldo})

    summary_df = pd.DataFrame(summary)

    # Tampilkan kotak-kotak saldo
    st.subheader("💰 Saldo Dompet")
    cols = st.columns(3)

    for i, row in summary_df.iterrows():
        with cols[i % 3]:
            st.metric(row["Dompet"], f"Rp {row['Saldo']:,.0f}")

    st.subheader("💼 Total Seluruh Saldo")
    total_saldo = summary_df["Saldo"].sum()
    st.metric("Total", f"Rp {total_saldo:,.0f}")

    st.divider()
    st.dataframe(summary_df.style.format({"Saldo": "{:,.0f}"}))


# =====================================================================
#                           2. TAMBAH DOMPET
# =====================================================================
with tab2:
    st.title("➕ Tambah Dompet Baru")

    wallet_name = st.text_input("Nama Dompet")
    if st.button("Simpan Dompet"):
        if wallet_name.strip() == "":
            st.error("Nama dompet tidak boleh kosong.")
        else:
            wallets_col.insert_one({"name": wallet_name})
            st.success("Dompet berhasil ditambahkan!")
            st.rerun()


# =====================================================================
#                          3. TRANSAKSI
# =====================================================================
with tab3:
    st.title("💸 Tambah Transaksi")

    wallets = load_wallets()
    df = load_transactions()

    trx_type = st.selectbox("Pilih Jenis Transaksi", ["Pemasukan", "Pengeluaran", "Transfer Antar Dompet"])

    amount = st.number_input("Jumlah", min_value=0)
    date = st.date_input("Tanggal", datetime.date.today())
    note = st.text_input("Catatan (opsional)")

    if trx_type == "Pemasukan":
        src = st.selectbox("Ke Dompet", wallets)

        if st.button("Tambah"):
            trx_col.insert_one({
                "type": "income",
                "source_id": src,
                "target_id": "",
                "amount": amount,
                "date": str(date),
                "note": note
            })
            st.success("Pemasukan berhasil dicatat!")
            st.rerun()

    elif trx_type == "Pengeluaran":
        src = st.selectbox("Dari Dompet", wallets)

        if st.button("Tambah"):
            trx_col.insert_one({
                "type": "expense",
                "source_id": src,
                "target_id": "",
                "amount": amount,
                "date": str(date),
                "note": note
            })
            st.success("Pengeluaran berhasil dicatat!")
            st.rerun()

    else:  # Transfer
        src = st.selectbox("Dari Dompet", wallets)
        dst = st.selectbox("Ke Dompet", wallets)

        if src == dst:
            st.error("Dompet asal dan tujuan tidak boleh sama.")
        else:
            if st.button("Transfer"):
                # transfer out
                trx_col.insert_one({
                    "type": "transfer_out",
                    "source_id": src,
                    "target_id": dst,
                    "amount": amount,
                    "date": str(date),
                    "note": note
                })
                # transfer in
                trx_col.insert_one({
                    "type": "transfer_in",
                    "source_id": src,
                    "target_id": dst,
                    "amount": amount,
                    "date": str(date),
                    "note": note
                })
                st.success("Transfer berhasil!")
                st.rerun()


# =====================================================================
#                         4. RIWAYAT TRANSAKSI
# =====================================================================
with tab4:
    st.title("📜 Riwayat Transaksi")

    df = load_transactions()

    if df.empty:
        st.info("Belum ada transaksi.")
    else:
        df_display = df[["date", "type", "amount", "note", "_id"]]
        st.dataframe(df_display)

        delete_id = st.text_input("Masukkan ID Transaksi yang ingin dihapus")
        if st.button("Hapus"):
            try:
                trx_col.delete_one({"_id": pd.to_datetime(delete_id)})
            except:
                trx_col.delete_one({"_id": delete_id})
            st.success("Transaksi berhasil dihapus!")
            st.rerun()


# =====================================================================
#                            5. LAPORAN
# =====================================================================
with tab5:
    st.title("📈 Laporan Keuangan")

    df = load_transactions()

    if df.empty:
        st.info("Belum ada data transaksi.")
    else:
        df["date"] = pd.to_datetime(df["date"])

        period = st.selectbox("Pilih Periode", ["Harian", "Mingguan", "Bulanan"])

        if period == "Harian":
            report = df.groupby(df["date"].dt.date)["amount"].sum()
        elif period == "Mingguan":
            report = df.groupby(df["date"].dt.isocalendar().week)["amount"].sum()
        else:
            report = df.groupby(df["date"].dt.month)["amount"].sum()

        st.line_chart(report)


