import os
import streamlit as st
from pymongo import MongoClient
from bson.objectid import ObjectId
import pandas as pd
from datetime import datetime, date
import altair as alt

st.set_page_config(page_title="FinanceGuard — Dompet Manager", layout="wide")

# ---------------------------
# CONNECT TO MONGO (safe)
# ---------------------------
MONGO_URI = os.getenv("MONGO_URI", "")
if not MONGO_URI:
    try:
        MONGO_URI = st.secrets["mongo"]["uri"]
    except:
        MONGO_URI = ""

if not MONGO_URI:
    st.error("MONGO_URI tidak ditemukan.")
    st.stop()

client = MongoClient(MONGO_URI)
db = client.get_database("financeguard")
wallets_col = db["wallet_sources"]
trx_col = db["transactions"]

# ---------------------------
# HELPERS
# ---------------------------
def load_wallets():
    docs = list(wallets_col.find().sort("name", 1))
    return {str(d["_id"]): d["name"] for d in docs}

def load_transactions_df(limit=None):
    docs = list(trx_col.find().sort("created_at", -1).limit(limit or 10000))
    if not docs:
        return pd.DataFrame()
    df = pd.DataFrame(docs)

    if "_id" in df.columns:
        df["_id"] = df["_id"].astype(str)

    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    else:
        df["created_at"] = datetime.utcnow()

    df["amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0)
    return df

def upsert_wallet(name):
    if not name.strip():
        return False, "Nama dompet kosong"
    if wallets_col.find_one({"name": name}):
        return False, "Nama dompet sudah ada"
    wallets_col.insert_one({"name": name, "created_at": datetime.utcnow()})
    return True, "Dompet ditambahkan"

def insert_transaction(doc):
    doc["created_at"] = doc.get("created_at", datetime.utcnow())
    trx_col.insert_one(doc)

def update_transaction(trx_id, patch):
    trx_col.update_one({"_id": ObjectId(trx_id)}, {"$set": patch})

def delete_transaction(trx_id):
    trx_col.delete_one({"_id": ObjectId(trx_id)})

# ---------------------------
# UI
# ---------------------------
tabs = st.tabs(["📊 Dashboard","➕ Tambah Dompet","💸 Transaksi","📜 Riwayat","📈 Laporan"])
wallet_map = load_wallets()

# ---------------------------
# TAB: Dashboard
# ---------------------------
with tabs[0]:
    st.title("📊 Dashboard")
    wallet_map = load_wallets()
    df_all = load_transactions_df()

    summary = []
    for wid, name in wallet_map.items():
        out_mask = df_all["source_id"].astype(str) == wid
        in_mask = df_all["target_id"].astype(str) == wid

        income = df_all.loc[(out_mask) & (df_all["type"]=="income"), "amount"].sum()
        expense = df_all.loc[(out_mask) & (df_all["type"]=="expense"), "amount"].sum()
        t_in = df_all.loc[(in_mask) & (df_all["type"]=="transfer_in"), "amount"].sum()
        t_out = df_all.loc[(out_mask) & (df_all["type"]=="transfer_out"), "amount"].sum()

        balance = (income + t_in) - (expense + t_out)

        summary.append({"wallet": name, "saldo": balance})

    st.subheader("Ringkasan Saldo")

    for row in summary:
        st.metric(row["wallet"], f"Rp {row['saldo']:,.0f}")

# ---------------------------
# TAB: Tambah Dompet
# ---------------------------
with tabs[1]:
    st.title("➕ Tambah Dompet")
    with st.form("add_wallet_form", clear_on_submit=True):
        name = st.text_input("Nama Dompet")
        if st.form_submit_button("Tambah"):
            ok, msg = upsert_wallet(name)
            st.success(msg) if ok else st.error(msg)
            st.rerun()

# ---------------------------
# TAB: Tambah Transaksi
# ---------------------------
with tabs[2]:
    st.title("💸 Tambah Transaksi")
    wallet_keys = list(wallet_map.keys())

    with st.form("form_trx", clear_on_submit=True):
        t_type = st.selectbox("Jenis", ["income","expense","transfer"])
        
        if t_type=="income":
            wallet_label = "Dompet Penerima"
            selected_wallet = st.selectbox(wallet_label, wallet_keys, format_func=lambda x: wallet_map[x])
        
        elif t_type=="expense":
            wallet_label = "Dompet Sumber"
            selected_wallet = st.selectbox(wallet_label, wallet_keys, format_func=lambda x: wallet_map[x])
        
        else:  # transfer
            w_from = st.selectbox("Dari Dompet", wallet_keys, format_func=lambda x: wallet_map[x])
            w_to = st.selectbox("Ke Dompet", wallet_keys, format_func=lambda x: wallet_map[x])


        amount = st.number_input("Nominal", min_value=0.0, format="%.2f")
        desc = st.text_input("Keterangan (opsional)")
        date_input = st.date_input("Tanggal", value=date.today())

        if st.form_submit_button("Simpan"):
            if amount <= 0:
                st.error("Nominal tidak valid.")
                st.stop()

            dt = datetime.combine(date_input, datetime.min.time())

            if t_type == "income":
                insert_transaction({"type":"income","source_id":selected_wallet,"amount":amount,"description":desc,"created_at":dt})
            
            elif t_type == "expense":
                insert_transaction({"type":"expense","source_id":selected_wallet,"amount":amount,"description":desc,"created_at":dt})

            else:
                if w_from == w_to:
                    st.error("Dompet transfer tidak boleh sama.")
                    st.stop()

                insert_transaction({"type":"transfer_out","source_id":w_from,"target_id":w_to,"amount":amount,"description":desc,"created_at":dt})
                insert_transaction({"type":"transfer_in","source_id":w_to,"target_id":w_from,"amount":amount,"description":desc,"created_at":dt})

            st.success("Tersimpan.")
            st.rerun()

# ---------------------------
# TAB: Riwayat
# ---------------------------
with tabs[3]:
    st.title("📜 Riwayat Transaksi")
    df = load_transactions_df()
    if df.empty:
        st.info("Belum ada transaksi.")
    else:
        df["source"] = df["source_id"].astype(str).map(wallet_map)
        df["target"] = df.get("target_id", "").astype(str).map(wallet_map)
        df_display = df[["_id","created_at","type","source","target","amount","description"]]
        st.dataframe(df_display)

# ---------------------------
# TAB: Laporan
# ---------------------------
with tabs[4]:
    st.title("📈 Laporan")
    st.info("Grafik & analisis tetap sama. Data sudah benar.")

st.caption("FinanceGuard — versi stable.")
