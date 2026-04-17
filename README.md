# 💰 FinanceGuard — Dompet Manager

Aplikasi berbasis **Streamlit** untuk mengelola keuangan pribadi secara sederhana namun powerful, dengan penyimpanan data menggunakan **MongoDB**.

---

## 🚀 Fitur Utama

### 📊 Dashboard

* Menampilkan saldo tiap dompet
* Total saldo keseluruhan
* Grafik tren pengeluaran harian

### ➕ Manajemen Dompet

* Tambah dompet (contoh: Cash, Bank, E-Wallet)
* Validasi agar tidak ada nama duplikat

### 💸 Transaksi

* Input 3 jenis transaksi:

  * Pemasukan (income)
  * Pengeluaran (expense)
  * Transfer antar dompet
* Validasi input (nominal & dompet)

### 📜 Riwayat Transaksi

* Melihat seluruh transaksi
* Filter berdasarkan:

  * Dompet
  * Jenis transaksi
  * Rentang tanggal
* Edit transaksi
* Hapus transaksi

### 📈 Laporan & Visualisasi

* Grafik berdasarkan:

  * Harian
  * Mingguan
  * Bulanan
* Filter lanjutan:

  * Dompet
  * Jenis transaksi
  * Tanggal
  * Keyword (search keterangan)
* Tabel ringkasan data

---

## 🧠 Cara Kerja Sistem

1. Data disimpan di MongoDB (database: `financeguard`)
2. Terdapat 2 collection utama:

   * `wallet_sources` → menyimpan data dompet
   * `transactions` → menyimpan transaksi
3. Setiap transaksi memiliki:

   * type (income / expense / transfer)
   * source_id
   * target_id
   * amount
   * created_at

---

## ⚙️ Cara Menjalankan

### 1. Install Dependencies

```bash
pip install streamlit pymongo pandas altair
```

### 2. Set MongoDB URI

Gunakan salah satu cara:

**Environment Variable**

```bash
export MONGO_URI="your_mongodb_uri"
```

**Atau Streamlit Secrets**

```toml
[mongo]
uri = "your_mongodb_uri"
```

### 3. Jalankan Aplikasi

```bash
streamlit run app.py
```

---

## 🎯 Kegunaan

Aplikasi ini digunakan untuk:

* Mencatat pemasukan dan pengeluaran
* Mengelola banyak dompet dalam satu tempat
* Melacak arus uang secara real-time
* Melihat histori transaksi dengan mudah

---

## 💡 Manfaat

### 1. Kontrol Keuangan Lebih Baik

Semua uang masuk dan keluar tercatat dengan jelas.

### 2. Monitoring Multi Dompet

Bisa mengelola banyak sumber uang (bank, cash, e-wallet).

### 3. Insight dari Data

Dengan grafik dan laporan, pengguna bisa:

* Melihat pola pengeluaran
* Mengetahui kebiasaan finansial

### 4. Fleksibel & Real-Time

Data langsung tersimpan di database dan bisa diakses kapan saja.

### 5. Minim Human Error

Perhitungan saldo dilakukan otomatis.

---

## 📊 Contoh Use Case

* Tracking pengeluaran harian
* Mengatur budget bulanan
* Monitoring cashflow pribadi
* Digunakan oleh mahasiswa atau pekerja

---

## 📌 Catatan

* Pastikan MongoDB aktif
* Pastikan URI benar
* Jangan gunakan nama dompet yang sama

---

## 🏁 Penutup

FinanceGuard membantu mengubah pencatatan keuangan yang biasanya manual menjadi sistem yang otomatis, rapi, dan mudah dianalisis.
