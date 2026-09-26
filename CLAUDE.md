# CLAUDE.md — Panduan Kerja untuk Claude di Repo NusaFlow

> Dokumen ini adalah rekap kerja (working memory) untuk siapa pun — manusia atau AI agent — yang melanjutkan pengembangan NusaFlow. `README.md` adalah sumber kebenaran teknis (cara install, API, deployment). `AGENTS.md` adalah spesifikasi/roadmap asli. **File ini adalah lapisan ketiga: status apa adanya + daftar gap yang nyata + rencana perbaikan yang konkret**, ditulis dari hasil membaca kode langsung (bukan asumsi).

---

## 1. Apa Ini

NusaFlow adalah **Supply Chain Control Tower** portofolio: visibilitas inventori → analitik → forecasting → rekomendasi replenishment → simulasi what-if. Semua data sintetis, jelas dinyatakan sebagai demonstrasi, bukan sistem produksi/enterprise sungguhan (lihat AGENTS.md §21).

7 fase roadmap asli **sudah semua diimplementasikan**, plus satu fase tambahan (Workspace/Auth) yang sengaja memperluas scope non-goal awal (AGENTS.md §5 sebelumnya melarang "large-scale multi-tenant SaaS" — ini versi portofolio-nya, bukan versi enterprise).

## 2. Tech Stack (verified dari kode, bukan cuma AGENTS.md)

| Layer | Stack |
|---|---|
| Frontend | Next.js 14.2.35 (pinned), React, TypeScript, Tailwind CSS, Recharts (satu-satunya charting lib) |
| Backend | Python 3.12 (bukan 3.13 — incompatibility dengan Pydantic 2.x), FastAPI, Pydantic, SQLAlchemy, Alembic (migrasi, bukan `create_all()`) |
| Database | SQLite (dev) / PostgreSQL via Supabase (prod) — sudah diverifikasi jalan di Postgres asli, bukan cuma diasumsikan |
| Auth | JWT Bearer (bukan session cookie) — dipilih karena frontend (Vercel) & backend (Render) beda origin; token disimpan di cookie non-httpOnly agar `middleware.ts` bisa gate route di server |
| ML/Forecasting | Pure Python, **tanpa** pandas/numpy/scikit-learn (AGENTS.md §23: jangan tambah dependency kalau belum perlu — di ~240 data point per pair, plain Python cukup) |
| Deploy target | Vercel (frontend) + Render (backend) + Supabase Postgres |
| Testing | `unittest`, dipisah jadi unit test per service + `test_api_endpoints.py` (full HTTP roundtrip via `TestClient`) |

## 3. Fitur yang Sudah Ada (per fase)

1. **Foundation** — schema relasional, seed data sintetis realistis, dashboard yang narik data asli dari API (bukan angka hardcoded).
2. **Inventory Intelligence** — avg daily demand, days of inventory, deteksi low/critical stock, stockout risk (`inventory_analysis.py`), dengan pagination + filter sku/warehouse.
3. **Shipment Monitoring** — status shipment yang dihitung live (`effective_status()`, `compute_delay_days()`) dari tanggal asli, bukan field statis; timeline event; simulasi "advance satu langkah" manual lewat tombol UI (karena tidak ada background scheduler — sengaja, biar tetap jalan di free-tier host).
4. **Alert Engine** — 6 rule (`LOW_STOCK`, `CRITICAL_STOCK`, `STOCKOUT_RISK`, `SHIPMENT_DELAY`, `SUPPLIER_DELAY`, `DEMAND_SPIKE`), reconciled terhadap tabel alerts (buka baru / refresh in-place / auto-resolve — tidak pernah duplikat).
5. **Demand Forecasting** — pipeline Historical → Cleaning (isi hari kosong dengan 0) → Feature engineering (multiplier hari-per-minggu dari histori asli) → dua model baseline (moving average vs weekday-seasonal) → backtest 14 hari terakhir, model dengan MAE terendah menang → forecast 30 hari ke depan dengan lower/upper bound dari residual asli.
6. **Replenishment Recommendation** — `max(Forecast Demand + Safety Stock - Current Stock - Incoming Stock, 0)`, setiap rekomendasi menyimpan input lengkap sehingga API bisa balikin `explanation` (arithmetic dalam bahasa manusia) — sesuai prinsip "every recommendation must be explainable".
7. **What-If Simulation** — 4 parameter (demand %, supplier lead-time delta, shipment delay delta, safety stock %), 5 metrik dibandingkan baseline vs skenario memakai fungsi kalkulasi yang sama persis (apples-to-apples). Read-only terhadap data operasional asli — hanya menulis ke tabel `SimulationScenario`/`SimulationResult` miliknya sendiri.
8. **Workspace/Auth (tambahan)** — setiap akun = 1 workspace; hampir semua tabel domain punya `workspace_id` dan difilter tiap query; uniqueness (kode warehouse, SKU) di-scope per-workspace; ada workspace demo bersama (`is_demo=True`) yang bisa direset admin, dan workspace baru mulai kosong (signup → 0 data).

## 4. ✅ Masalah Utama: "Workspace Kosong = Fitur Turunan Dead-End" — SUDAH DITUTUP

> **Status (update terakhir): kedua gejala di bawah sudah selesai ditangani.** Lihat §5.1 dan §5.2 untuk rancangannya — semuanya sudah diimplementasikan, sudah ada test isolasi workspace (`EmptyWorkspaceOnboardingTest` di `test_api_endpoints.py`, 117 test lulus), dan README sudah di-update (endpoint list + Known limitations). Bagian §4 dan §5 di bawah dipertahankan sebagai catatan mengapa perbaikan ini dibutuhkan dan apa saja yang dipenuhi; jangan dianggap TODO yang masih terbuka.

Ini kategori masalah tunggal yang paling penting untuk diperbaiki, dengan dua gejala konkret yang sudah dikonfirmasi langsung di kode:

### 4a. Tidak ada cara mengisi demand history di UI/API
- `POST /api/v1/inventory` bisa langsung menambahkan stock record baru → langsung muncul di Inventory Intelligence dan langsung bisa kena alert LOW_STOCK/CRITICAL_STOCK (karena itu cuma butuh on-hand vs safety stock).
- Tapi `generate_forecast_for_pair()` (Phase 5) butuh `DemandRecord` historis asli, dan replenishment (Phase 6) butuh forecast itu sudah ada dulu.
- **Akibatnya:** workspace baru yang baru signup — walaupun sudah isi warehouse, produk, dan stock — akan selalu dapat "not enough demand history yet" begitu memanggil `POST /forecasts/generate`. Forecast, Replenishment, dan simulasi yang bergantung padanya jadi tidak bisa dicoba sama sekali. Ini sudah disebutkan eksplisit di README bagian "Known limitations" sebagai gap berikutnya yang paling jelas untuk ditutup.
- Konfirmasi kode: tidak ada endpoint `POST /api/v1/demand` atau semacamnya di `main.py` — hanya `GET /api/v1/demand`.

### 4b. Tidak ada cara membuat Shipment secara manual
- Endpoint yang ada untuk shipment hanya: `GET /shipments`, `GET /shipments/{id}`, `GET /shipments/{id}/events`, `POST /shipments/{id}/simulate/advance`.
- Tidak ada `POST /api/v1/shipments` untuk membuat shipment baru dari nol.
- Konfirmasi kode: `frontend/app/dashboard/shipments/page.tsx` hanya berisi list + filter status, tidak ada form/state untuk membuat shipment baru (dibandingkan dengan Inventory/Suppliers page yang punya `activeForm` / form CRUD).
- **Akibatnya:** workspace baru tidak bisa mencoba Phase 3 (shipment tracking + simulate-advance) sama sekali, karena shipment hanya bisa muncul lewat seed data demo — bukan dibuat manual.

**Pola umum:** dua gejala ini adalah instansiasi dari masalah yang sama — beberapa fitur turunan (forecast, replenishment, simulation, shipment tracking) hanya bisa dijalankan di atas data yang sebelumnya cuma bisa masuk lewat seed script, bukan lewat CRUD yang tersedia untuk pengguna workspace baru. Workspace demo terasa lengkap; workspace baru terasa seperti setengah aplikasi.

## 5. Rencana Perbaikan yang Diminta (dan direkomendasikan)

### 5.1. ✅ Form "Estimasi Cepat" untuk demand history (prioritas tinggi)

Ide inti: user cukup masukkan **perkiraan unit terjual per hari**, sistem generate histori dasar dari angka itu dengan variasi wajar — dan **ditandai jelas sebagai estimasi**, bukan data asli. Ini pendekatan paling proporsional untuk prototype: cepat, jujur soal sifatnya, dan langsung membuka semua fitur turunan (Forecast, Replenishment, alert DEMAND_SPIKE, Simulation).

**Rancangan konkret:**

- **Backend — endpoint baru** `POST /api/v1/demand/quick-estimate`
  - Body: `{ sku, warehouse, avg_units_per_day, days_back? }` (default `days_back` cukup untuk backtest 14 hari + histori wajar, mis. 60–90 hari, sejalan dengan `DEMAND_HISTORY_DAYS` yang sudah dipakai `seed.py`).
  - Logika: pakai generator variasi yang **sama** dengan yang sudah dipakai `seed.py` (weekday multiplier + noise acak dengan RNG seeded) supaya konsisten secara statistik dengan data demo asli — jangan bikin generator baru yang beda perilaku. Reuse fungsi, jangan duplikasi (AGENTS.md §22.3: reuse existing abstractions).
  - **Tandai eksplisit sebagai estimasi**: tambah kolom `is_estimated: bool` (default `False`) di `DemandRecord`, migrasi Alembic baru. Baris yang dibuat lewat endpoint ini di-set `is_estimated=True`.
  - Response: konfirmasi jumlah hari yang di-generate + rentang tanggal, supaya user tahu persis apa yang baru terjadi.
- **Frontend — di halaman Inventory** (atau tab baru "Demand History" di halaman produk):
  - Form kecil: pilih SKU/warehouse (dari pasangan yang sudah ada di Inventory), input "kira-kira berapa unit per hari", tombol "Generate estimasi & buka Forecast".
  - Setelah submit sukses, tampilkan badge/banner **"Estimasi, bukan data historis asli"** di halaman Forecast dan Replenishment untuk pair tersebut (baca `is_estimated` dari data demand yang mendasari forecast pair itu).
  - Auto-trigger `POST /forecasts/generate?sku=&warehouse=` lalu `POST /replenishment/generate?sku=&warehouse=` setelah histori berhasil dibuat, supaya user langsung lihat hasilnya tanpa harus tahu ada 2 langkah manual di belakang.
- **UI/label kejujuran (penting, sesuai prinsip AGENTS.md §5.1 Forecast — "Estimated demand" bukan "Guaranteed demand")**: chart forecast dan tabel replenishment untuk pair yang datanya estimasi harus menunjukkan indikator visual (ikon/badge kuning, bukan hijau/biru seperti data asli) sehingga tidak tertukar dengan hasil dari data demo asli.
- **Test yang perlu ditambah**: unit test generator estimasi (variasi tidak nol, weekday pattern konsisten), test endpoint (badge `is_estimated` konsisten di response demand + forecast), test bahwa forecast/replenishment berhasil di-generate setelah estimasi dibuat.

### 5.2. ✅ Shipment Manual (prioritas tinggi — setara dengan 5.1)

- **Backend — endpoint baru** `POST /api/v1/shipments`
  - Body minimal: `supplier_id, warehouse_id, product_id?, quantity, eta_date` (atau `transit_days` lalu backend hitung `eta_date`), status awal `PENDING` atau `IN_TRANSIT` (biarkan user pilih, default `PENDING` supaya konsisten dengan alur "Created → Departed" yang sudah ada di `simulate/advance`).
  - Reuse `effective_status()`/`compute_delay_days()` yang sudah ada — jangan bikin logika status baru; shipment yang dibuat manual harus otomatis kompatibel dengan tombol "Simulate next step" yang sudah ada.
  - Validasi: `supplier_id`/`warehouse_id` harus milik workspace yang sama (workspace isolation — ini prinsip paling penting di proyek ini, lihat `test_workspace_isolation_across_two_accounts`).
- **Frontend — halaman Shipments**: tambah tombol "+ Tambah Shipment" yang membuka form (pola yang sama seperti `activeForm` di Inventory page), pilih supplier & warehouse dari dropdown data yang sudah ada, submit → shipment baru muncul di list dan bisa langsung diklik untuk "Simulate next step".
- **Test**: tambahan di `test_shipment_service.py` dan `test_api_endpoints.py` untuk create + workspace isolation pada endpoint baru ini.

### 5.3. Gap Lain yang Sepadan (kategori sama: "workspace baru terbatas")

- **Tidak ada cara menambah `ShipmentEvent` manual** selain lewat `simulate/advance` — cukup sebagai catatan, karena `simulate/advance` sudah menutupi use-case utamanya; tidak perlu endpoint terpisah kecuali ada kebutuhan spesifik menunjukkan event history yang lebih kaya.
- **Tidak ada bulk-import** (CSV) untuk inventory/produk/warehouse di workspace baru — untuk portofolio, form satu-per-satu (yang sudah ada) mungkin cukup, tapi kalau user ingin mendemonstrasikan skala (20 SKU, 3 warehouse dari AGENTS.md §4), input manual satu-satu jadi lambat. Pertimbangkan "generate contoh data" (mirip semangat 5.1) sebagai tombol "Isi dengan data contoh" di workspace baru — opsional, prioritas rendah.
- **Tidak ada scheduler**, ini sudah didokumentasikan sebagai keputusan sadar (free-tier constraint), bukan bug — tidak perlu diperbaiki, hanya perlu tetap dijaga agar tidak "diperbaiki" secara tidak sengaja dengan menambah worker/cron yang justru melanggar AGENTS.md §7 (free-tier constraint) dan §24 (jangan buru-buru menambah kompleksitas infrastruktur).
- **In-memory cache per-process** dan **Next.js versi lama dengan CVE yang sudah dianalisis tidak applicable** — keduanya sudah didokumentasikan dengan alasan jelas di README "Known limitations"; tidak mendesak, tapi upgrade Next.js ke v15/16 tetap perlu masuk backlog sebagai pekerjaan terpisah (breaking change, butuh testing sendiri — jangan drive-by bump, sesuai catatan README sendiri).

### 5.4. Prioritas Pengerjaan (disarankan)

> **Status: item 1–4 selesai.** Hanya item 5 yang tersisa, dan memang sengaja dibiarkan terbuka (opsional, prioritas rendah).

1. ✅ `is_estimated` migration + quick-estimate endpoint & generator (5.1) — ini yang paling langsung membuka fitur lain. *Kolom `DemandRecord.is_estimated` + migrasi Alembic ke-7, `POST /api/v1/demand/quick-estimate` di `main.py` dengan generator yang di-reuse dari `seed.py`.*
2. ✅ Form estimasi cepat di frontend + badge "ini estimasi" di Forecast/Replenishment. *`EstimateDemandForm` di Inventory page, `EstimatedDataBadge` di `components/ui.tsx`, badge + chart berubah amber di Forecast, badge di tabel + panel "Why this number?" di Replenishment.*
3. ✅ `POST /api/v1/shipments` (5.2) + form di frontend. *Logika tetap di service layer; `effective_status()`/`compute_delay_days()` di-reuse; form `AddShipmentForm` di Shipments page.*
4. ✅ Test coverage untuk keduanya (unit + endpoint + workspace isolation). *117 test lulus (`python -m unittest discover tests`); `EmptyWorkspaceOnboardingTest` menguji alur lengkap workspace baru.*
5. ⬜ (Opsional, prioritas rendah) tombol "isi dengan data contoh" untuk seluruh workspace baru sekaligus, dan upgrade Next.js sebagai pekerjaan terpisah.

## 6. Aturan Kerja untuk Agent yang Melanjutkan (ringkasan dari AGENTS.md §22, ditegaskan ulang)

- Baca `README.md` dulu untuk state aktual, `AGENTS.md` untuk filosofi/non-goals, file ini untuk gap & rencana.
- Jangan tambah dependency baru untuk hal yang bisa diselesaikan dengan pola yang sudah ada (mis. generator variasi demand — reuse punya `seed.py`, jangan bikin pustaka statistik baru).
- Business logic tetap di service layer (`app/*_service.py`), bukan di route handler atau komponen React.
- Setiap fitur baru yang menyentuh data cross-workspace **wajib** diuji isolasinya (pola `test_workspace_isolation_across_two_accounts`).
- Update `README.md` (endpoint list, known limitations) begitu gap di §4 sudah ditutup — jangan biarkan README bilang "belum ada" untuk sesuatu yang sudah dibangun.