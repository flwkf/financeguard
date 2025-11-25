# app.py
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
# try streamlit secrets if env not present
if not MONGO_URI:
    try:
        MONGO_URI = st.secrets["mongo"]["uri"]
    except Exception:
        MONGO_URI = ""

if not MONGO_URI:
    st.error("MONGO_URI tidak ditemukan. Set environment variable MONGO_URI atau tambah [mongo].uri di .streamlit/secrets.toml")
    st.stop()

client = MongoClient(MONGO_URI)
db = client.get_database("financeguard")  # gunakan db bernama financeguard
wallets_col = db["wallet_sources"]
trx_col = db["transactions"]

# ---------------------------
# HELPERS
# ---------------------------
def load_wallets():
    docs = list(wallets_col.find().sort("name", 1))
    return {str(d["_id"]): d["name"] for d in docs}

def load_transactions_df(limit=None):
    docs = list(trx_col.find().sort("created_at", -1).limit(limit if limit else 10000))
    if not docs:
        return pd.DataFrame(columns=["_id","type","source_id","target_id","amount","description","created_at","date","note"])
    df = pd.DataFrame(docs)
    # normalize columns
    for c in ["type","source_id","target_id","amount","description","created_at","date","note"]:
        if c not in df.columns:
            df[c] = None
    # convert types
    if "_id" in df.columns:
        df["_id"] = df["_id"].astype(str)
    # ensure datetime
    if df["created_at"].notna().any():
        try:
            df["created_at"] = pd.to_datetime(df["created_at"])
        except Exception:
            # maybe saved as string date
            df["created_at"] = pd.to_datetime(df["created_at"].astype(str), errors="coerce")
    else:
        df["created_at"] = pd.to_datetime(df["date"].astype(str), errors="coerce")
    # ensure numeric amount
    df["amount"] = pd.to_numeric(df["amount"].fillna(0), errors="coerce").fillna(0)
    return df

def upsert_wallet(name):
    if not name or str(name).strip()=="":
        return False, "Nama dompet kosong"
    # prevent duplicate names (optional)
    if wallets_col.find_one({"name": name.strip()}):
        return False, "Nama dompet sudah ada"
    wallets_col.insert_one({"name": name.strip(), "created_at": datetime.utcnow()})
    return True, "Dompet ditambahkan"

def insert_transaction(doc):
    doc = dict(doc)
    doc.setdefault("created_at", datetime.utcnow())
    trx_col.insert_one(doc)

def update_transaction(trx_id, patch: dict):
    trx_col.update_one({"_id": ObjectId(trx_id)}, {"$set": patch})

def delete_transaction(trx_id):
    trx_col.delete_one({"_id": ObjectId(trx_id)})

# ---------------------------
# UI: Tabs
# ---------------------------
tabs = st.tabs(["📊 Dashboard","➕ Tambah Dompet","💸 Transaksi","📜 Riwayat","📈 Laporan"])
wallet_map = load_wallets()

# ---------------------------
# DASHBOARD TAB
# ---------------------------
with tabs[0]:
    st.title("📊 Dashboard")
    # reload data
    wallet_map = load_wallets()
    df_all = load_transactions_df()

    # ensure columns exist
    for col in ["source_id","target_id","type","amount"]:
        if col not in df_all.columns:
            df_all[col] = None

    # compute saldo per wallet
    summary = []
    for wid, name in wallet_map.items():
        out_mask = df_all["source_id"].astype(str) == wid
        in_mask  = df_all["target_id"].astype(str) == wid

        income = df_all.loc[out_mask & (df_all["type"]=="income"), "amount"].sum()
        expense = df_all.loc[out_mask & (df_all["type"]=="expense"), "amount"].sum()
        t_in = df_all.loc[in_mask & (df_all["type"]=="transfer_in"), "amount"].sum()
        t_out = df_all.loc[out_mask & (df_all["type"]=="transfer_out"), "amount"].sum()

        bal = (income + t_in) - (expense + t_out)
        summary.append({"wallet_id": wid, "wallet": name, "saldo": bal})

    summary_df = pd.DataFrame(summary)
    total_all = summary_df["saldo"].sum() if not summary_df.empty else 0

    # show metrics cards - responsive: 4 per row
    st.subheader("Ringkasan Saldo")
    if summary_df.empty:
        st.info("Belum ada dompet atau transaksi.")
    else:
        per_row = 4
        cols = st.columns(per_row)
        for i, row in summary_df.iterrows():
            c = cols[i % per_row]
            c.metric(label=row["wallet"], value=f"Rp {row['saldo']:,.0f}")

        st.metric("💰 Total Seluruh Dompet", f"Rp {total_all:,.0f}")

    st.markdown("---")
    # mini charts: pengeluaran per hari (Altair)
    st.subheader("Tren Pengeluaran Harian (semua dompet)")
    df_exp = df_all[df_all["type"]=="expense"].copy()
    if not df_exp.empty:
        df_exp["date_only"] = df_exp["created_at"].dt.date
        daily = df_exp.groupby("date_only", as_index=False)["amount"].sum()
        chart = alt.Chart(daily).mark_line(point=True).encode(
            x=alt.X("date_only:T", title="Tanggal"),
            y=alt.Y("amount:Q", title="Total Pengeluaran (Rp)"),
            tooltip=[alt.Tooltip("date_only:T", title="Tanggal"), alt.Tooltip("amount:Q", title="Total (Rp)")]
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Belum ada data pengeluaran untuk ditampilkan.")

# ---------------------------
# TAB: Tambah Dompet
# ---------------------------
with tabs[1]:
    st.title("➕ Tambah Dompet")
    with st.form("form_add_wallet", clear_on_submit=True):
        new_name = st.text_input("Nama Dompet (contoh: Mandiri, ShopeePay, Cash)")
        sub = st.form_submit_button("Tambah Dompet")
        if sub:
            ok, msg = upsert_wallet(new_name)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ---------------------------
# TAB: Transaksi (input)
# ---------------------------
with tabs[2]:
    st.title("💸 Tambah Transaksi")
    wallet_map = load_wallets()

    if not wallet_map:
        st.info("Belum ada dompet. Tambah dompet dulu di tab 'Tambah Dompet'.")
    else:
        wallet_keys = list(wallet_map.keys())

        with st.form("form_trx", clear_on_submit=True):
            ttype = st.selectbox("Jenis Transaksi", ["income","expense","transfer"])

            if ttype == "income":
                w_to = st.selectbox(
                    "Dompet Tujuan",
                    wallet_keys,
                    format_func=lambda k: wallet_map[k]
                )

            elif ttype == "expense":
                w_from = st.selectbox(
                    "Dompet Sumber",
                    wallet_keys,
                    format_func=lambda k: wallet_map[k]
                )
            elif ttype == "transfer":
                # ⬇⬇⬇ INI YANG DIPERBAIKI (PASTI MUNCUL)
                w_from = st.selectbox(
                    "Dari (Dompet)",
                    wallet_keys,
                    format_func=lambda k: wallet_map[k]
                )
                w_to = st.selectbox(
                    "Ke (Dompet)",
                    wallet_keys,
                    format_func=lambda k: wallet_map[k]
                )

            amount = st.number_input("Nominal (Rp)", min_value=0.0, format="%.2f")
            desc = st.text_input("Deskripsi / Catatan (opsional)")
            date_input = st.date_input("Tanggal transaksi", value=date.today())

            submit = st.form_submit_button("Simpan Transaksi")

            if submit:
                if amount <= 0:
                    st.error("Nominal harus lebih besar dari 0")
                    st.stop()

                if ttype == "income":
                    insert_transaction({
                        "type": "income",
                        "source_id": w_to,
                        "target_id": None,
                        "amount": float(amount),
                        "description": desc,
                        "created_at": datetime.combine(date_input, datetime.min.time())
                    })

                elif ttype == "expense":
                    insert_transaction({
                        "type": "expense",
                        "source_id": w_from,
                        "target_id": None,
                        "amount": float(amount),
                        "description": desc,
                        "created_at": datetime.combine(date_input, datetime.min.time())
                    })

                elif ttype == "transfer":
                    if w_from == w_to:
                        st.error("Dompet asal dan tujuan tidak boleh sama")
                        st.stop()

                    insert_transaction({
                        "type": "transfer_out",
                        "source_id": w_from,
                        "target_id": w_to,
                        "amount": float(amount),
                        "description": desc,
                        "created_at": datetime.combine(date_input, datetime.min.time())
                    })
                    insert_transaction({
                        "type": "transfer_in",
                        "source_id": w_from,
                        "target_id": w_to,
                        "amount": float(amount),
                        "description": desc,
                        "created_at": datetime.combine(date_input, datetime.min.time())
                    })

                st.success("Transaksi berhasil disimpan")
                st.rerun()

# ---------------------------
# TAB: Riwayat (edit / delete / filter)
# ---------------------------
with tabs[3]:
    st.title("📜 Riwayat Transaksi")
    wallet_map = load_wallets()
    df = load_transactions_df()

    # filters
    st.markdown("#### Filter")
    col1, col2, col3 = st.columns(3)
    with col1:
        f_wallet = st.selectbox("Filter Dompet (semua)", ["Semua"] + list(wallet_map.values()))
    with col2:
        f_type = st.selectbox("Jenis (semua)", ["Semua","income","expense","transfer_in","transfer_out"])
    with col3:
        f_from = st.date_input("Dari tanggal", value=None)
        f_to = st.date_input("Sampai tanggal", value=None)

    df["src_name"] = df["source_id"].astype(str).map(wallet_map)
    df["tgt_name"] = df["target_id"].astype(str).map(wallet_map)
    # apply filters
    mask = pd.Series([True]*len(df))
    if f_wallet != "Semua":
        mask = mask & ((df["src_name"]==f_wallet) | (df["tgt_name"]==f_wallet))
    if f_type != "Semua":
        mask = mask & (df["type"]==f_type)
    if f_from:
        mask = mask & (df["created_at"].dt.date >= f_from)
    if f_to:
        mask = mask & (df["created_at"].dt.date <= f_to)

    dff = df[mask].copy()
    if dff.empty:
        st.info("Tidak ada transaksi sesuai filter.")
    else:
        # display table
        dff_display = dff[["_id","created_at","type","src_name","tgt_name","amount","description"]].rename(
            columns={"_id":"ID","created_at":"Waktu","type":"Jenis","src_name":"Sumber","tgt_name":"Tujuan","amount":"Nominal","description":"Keterangan"}
        )
        st.dataframe(dff_display)

        # select for edit/delete
        sel_id = st.selectbox("Pilih ID transaksi untuk edit/hapus", dff["_id"].tolist())
        sel_row = dff[dff["_id"]==sel_id].iloc[0]

        st.markdown("#### Hapus Transaksi")
        if st.button("🗑 Hapus transaksi ini"):
            try:
                delete_transaction(sel_id)
                st.success("Transaksi dihapus")
                st.rerun()
            except Exception as e:
                st.error("Gagal menghapus: " + str(e))

        st.markdown("#### Edit Transaksi (nominal & keterangan)")
        with st.form("form_edit_trx"):
            new_amount = st.number_input("Nominal (Rp)", min_value=0.0, value=float(sel_row["amount"]))
            new_desc = st.text_input("Keterangan", value=sel_row.get("description","") or "")
            # optionally change type or wallets
            new_type = st.selectbox("Jenis", ["income","expense","transfer_in","transfer_out"], index=["income","expense","transfer_in","transfer_out"].index(sel_row["type"]) if sel_row["type"] in ["income","expense","transfer_in","transfer_out"] else 0)
            src_choices = list(wallet_map.keys())
            tgt_choices = list(wallet_map.keys())
            # default indices
            try:
                src_idx = src_choices.index(sel_row["source_id"])
            except Exception:
                src_idx = 0
            try:
                tgt_idx = tgt_choices.index(sel_row["target_id"]) if sel_row["target_id"] else 0
            except Exception:
                tgt_idx = 0

            new_src = st.selectbox("Sumber (Dompet)", src_choices, index=src_idx, format_func=lambda k: wallet_map[k])
            new_tgt = st.selectbox("Tujuan (Dompet)", ["None"] + tgt_choices, index=(1+tgt_idx) if sel_row["target_id"] else 0, format_func=lambda k: wallet_map[k] if k!="None" else "None")
            submit_edit = st.form_submit_button("Simpan Perubahan")

            if submit_edit:
                patch = {
                    "amount": float(new_amount),
                    "description": new_desc,
                    "type": new_type,
                    "source_id": new_src
                }
                if new_tgt != "None":
                    patch["target_id"] = new_tgt
                else:
                    patch["target_id"] = None
                try:
                    update_transaction(sel_id, patch)
                    st.success("Transaksi diperbarui")
                    st.rerun()
                except Exception as e:
                    st.error("Gagal update: " + str(e))

# ---------------------------
# TAB: Laporan (Altair full)
# ---------------------------
with tabs[4]:
    st.title("📈 Laporan & Visualisasi")
    wallet_map = load_wallets()
    df = load_transactions_df()

    # ensure datetime
    if df.empty:
        st.info("Belum ada transaksi untuk laporan.")
    else:
        st.subheader("Filter Laporan")
        col1,col2,col3 = st.columns(3)
        with col1:
            sel_wallet = st.selectbox("Pilih Dompet (Semua)", ["Semua"] + list(wallet_map.values()))
        with col2:
            sel_kind = st.selectbox("Jenis Laporan", ["Pengeluaran", "Pemasukan", "Semua"])
        with col3:
            sel_period = st.selectbox("Periode", ["Harian","Mingguan","Bulanan"])

        # prepare df for charts
        df_chart = df.copy()
        df_chart["wallet_src"] = df_chart["source_id"].astype(str).map(wallet_map)
        df_chart["wallet_tgt"] = df_chart["target_id"].astype(str).map(wallet_map)
        df_chart["date_only"] = df_chart["created_at"].dt.date

        # filter wallet
        if sel_wallet != "Semua":
            df_chart = df_chart[(df_chart["wallet_src"]==sel_wallet) | (df_chart["wallet_tgt"]==sel_wallet)]

        # filter kind
        if sel_kind == "Pengeluaran":
            df_chart = df_chart[df_chart["type"]=="expense"]
        elif sel_kind == "Pemasukan":
            df_chart = df_chart[df_chart["type"]=="income"]

        if df_chart.empty:
            st.info("Tidak ada data setelah filter.")
        else:
            if sel_period == "Harian":
                agg = df_chart.groupby("date_only", as_index=False)["amount"].sum()
                agg = agg.rename(columns={"date_only":"Tanggal","amount":"Total"})
                chart = alt.Chart(agg).mark_line(point=True).encode(
                    x=alt.X("Tanggal:T"),
                    y=alt.Y("Total:Q"),
                    tooltip=["Tanggal","Total"]
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
            elif sel_period == "Mingguan":
                df_chart["week"] = pd.to_datetime(df_chart["created_at"]).dt.to_period("W").apply(lambda r: r.start_time)
                agg = df_chart.groupby("week", as_index=False)["amount"].sum()
                agg = agg.rename(columns={"week":"Minggu","amount":"Total"})
                chart = alt.Chart(agg).mark_bar().encode(
                    x=alt.X("Minggu:T"),
                    y=alt.Y("Total:Q"),
                    tooltip=["Minggu","Total"]
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
            else:
                df_chart["month"] = pd.to_datetime(df_chart["created_at"]).dt.to_period("M").astype(str)
                agg = df_chart.groupby("month", as_index=False)["amount"].sum()
                agg = agg.rename(columns={"month":"Bulan","amount":"Total"})
                chart = alt.Chart(agg).mark_area(opacity=0.5).encode(
                    x=alt.X("Bulan:T"),
                    y=alt.Y("Total:Q"),
                    tooltip=["Bulan","Total"]
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)

        st.markdown("---")
        st.subheader("Tabel Ringkasan")
        # show aggregated table
        st.dataframe(df_chart[["_id","created_at","type","wallet_src","wallet_tgt","amount","description"]].rename(columns={
            "_id":"ID","created_at":"Waktu","type":"Jenis","wallet_src":"Sumber","wallet_tgt":"Tujuan","amount":"Nominal","description":"Keterangan"
        }))

# ---------------------------
# END
# ---------------------------
st.caption("FinanceGuard — versi premium. Pastikan MONGO_URI diset di environment atau secrets.")
