---
name: agathon-heartbeat-proactive
description: >-
  Heartbeat profiling untuk Sir Agathon berbasis Otto-Realm. Gunakan saat heartbeat untuk membaca sinyal energi, fokus, kebingungan, overload, recovery, dan pola kerja; lalu menyesuaikan gaya bantuan secara adaptif. Profil neuro (AuDHD dan komorbid kelemahan kognitif) dipakai sebagai konteks operasional yang dideklarasikan user, bukan diagnosis.
triggers:
  keywords:
    - "heartbeat profile"
    - "profiling heartbeat"
    - "AuDHD"
    - "cognitive weakness"
    - "adaptive support"
    - "proactive checkin"
  suppress_if: [hygiene-check, package-install-only]
priority: 9
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: heartbeat_profile_delta
model_hint: standard
escalate_to: agathon-soft-profile
memory_anchor:
  - "C:\\Users\\joshu\\Josh Obsidian\\.Otto-Realm\\Profile Snapshot.md"
  - "state/handoff/latest.json"
  - "artifacts/reports/kairos_daily_strategy.md"
constraints:
  - no-false-confidence
  - cite-specifics
  - no-medical-diagnosis
  - practical-support-only
checkpoint_required: true
---

# Agathon Heartbeat Proactive

Skill ini untuk profiling adaptif per-heartbeat.

## Prinsip

- Anggap AuDHD + komorbid weakness sebagai konteks kerja yang user deklarasikan.
- Jangan diagnosa medis.
- Jangan mengarang emosi/trait.
- Gunakan bukti kecil tapi konsisten.
- Selalu keluarkan 1 langkah kecil yang bisa langsung dijalankan.

## Sumber Bukti Wajib

1. `state/handoff/latest.json`
2. `state/checkpoints/pipeline.json`
3. `artifacts/reports/kairos_daily_strategy.md`
4. `artifacts/reports/dream_summary.md`
5. Otto-Realm anchor:
   - `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Profile Snapshot.md`
   - latest `Heartbeats/*.md` bila ada

## Data yang Dikumpulkan Proaktif

- friction_signals:
  - confusion loop
  - context switching tinggi
  - kehilangan thread
  - delay memulai
- capacity_signals:
  - energi rendah/sedang/tinggi
  - fokus pendek/panjang
  - toleransi kompleksitas
- recovery_signals:
  - apa yang memulihkan ritme
  - format instruksi yang paling kebantu

## Workflow Heartbeat

1. Baca paket status dan handoff terbaru.
2. Ekstrak 3-5 sinyal objektif.
3. Bandingkan dengan profil Otto-Realm terakhir.
4. Hitung `support_mode`:
   - `stabilize`: saat overload/confusion tinggi
   - `focus`: saat energi cukup, perlu narrowing
   - `build`: saat stabil, siap naik tingkat
5. Tulis output schema.
6. Simpan delta kecil ke state/handoff atau note heartbeat (jika diminta alur tulis).

## Output schema: heartbeat_profile_delta

- `evidence`
- `support_mode`
- `risk_signals`
- `recovery_levers`
- `next_micro_step`
- `prompt_style`

## Prompt Style Adaptif

- Untuk overload:
  - kalimat pendek
  - 1 aksi utama
  - tanpa opsi berlebih
- Untuk mode fokus:
  - 1 tujuan
  - 3 checklist maksimal
- Untuk mode build:
  - 1 milestone
  - 1 metrik selesai

## Larangan

- Tidak boleh menyimpulkan kondisi medis baru.
- Tidak boleh memaksa framing motivasional kosong.
- Tidak boleh memberi banyak tugas paralel saat `support_mode=stabilize`.
