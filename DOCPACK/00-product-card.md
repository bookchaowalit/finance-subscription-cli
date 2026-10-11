---
title: Subscription Intelligence — Product Card
doc_id: CARD-subscription-intelligence
doc_type: product-card
verdict: showcase
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Subscription Intelligence — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

ช่วยเจ้าของหา subscription ที่จ่ายอยู่จากอีเมลใบเสร็จ/ต่ออายุ เทียบกับหลักฐานการใช้งานในปฏิทิน แล้วแนะนำ Keep/Downgrade/Cancel โดยไม่แก้ไขอีเมลใด ๆ

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ค่าสมาชิก SaaS/บริการสะสมจนลืม ทั้ง trial ที่ต่ออายุอัตโนมัติและการขึ้นราคา
- ผู้ใช้: เจ้าของคนเดียว (personal subscriptions)

## 3. สิ่งที่ทำได้จริงตอนนี้

- `gmail_adapter/client.py` ค้น Gmail แบบอ่านอย่างเดียวด้วย query ด้านใบเสร็จ/ต่ออายุ ผ่าน Google OAuth จาก environment (`infra_bridge`); ไม่เก็บเนื้อหาอีเมลเต็ม
- `extractors/signals.py`, `calendar_adapter.py`, `subscription_registry/store.py`, `scoring/worth.py` (3 ชั้น), `recommendations/engine.py`, `reports/builder.py`
- CLI `bin/subscription-intel`; schema JSON 2 ไฟล์; test 1 ไฟล์ (extractors)
- การยกเลิกเป็นเพียง checklist ร่างให้มนุษย์อนุมัติ

## 4. หลักฐานสถานะ

- Stack: Python
- Commits: 3 (แรก 2026-07-25 → ล่าสุด 2026-08-11), branch `main`; working tree สะอาด
- Source: 19 ไฟล์ / 1,521 บรรทัด; test 1 ไฟล์
- CI: 0 workflow (ไม่มี CI)
- Deploy config: ไม่มี
- Live URL: ไม่พบใน repo

## 5. คุณค่าและจุดต่าง

- แก้ปัญหาจริงของเจ้าของ และอาจประหยัดเงินได้ทันที **[สมมติฐาน: ยังไม่มีตัวเลขเงินที่ประหยัด]**
- คู่แข่ง (Rocket Money ฯลฯ) ใช้ข้อมูลธนาคารและไม่รองรับไทย; การใช้ Gmail เป็นจุดต่างที่ใช้ได้กับคนไทย **[สมมติฐาน]**

## 6. ช่องว่างสำคัญ

- commit 3 ครั้ง ไม่มีการแก้ตั้งแต่ 2026-08-11 ไม่มี CI และมี test เพียงไฟล์เดียว
- ไม่มีหลักฐานว่ารันกับกล่องจดหมายจริงและได้รายงานที่ใช้ตัดสินใจ **[ต้องยืนยัน]**
- ผูกกับ OAuth ของ Solo Empire จึงใช้กับผู้ใช้อื่นไม่ได้

## 7. คำตัดสิน

**showcase** — ปัญหาจริงและ core ครบโครง แต่ยังไม่มีหลักฐานว่าใช้งานจริงและหยุดพัฒนาแล้วเกือบสองเดือน จึงยังไม่ถึงระดับลงทุน

จะเป็น `invest` ทันทีที่รันกับกล่องจดหมายจริงหนึ่งรอบแล้วพบ subscription ที่ยกเลิกได้และบันทึกจำนวนเงินที่ประหยัด

## 8. ขั้นต่อไป

1. รันรายงานจริงหนึ่งรอบและบันทึกผล (จำนวน subscription, เงินที่ประหยัดได้)
2. เพิ่ม CI และ test ของ scoring/recommendations

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอพิจารณา | — | ________ |

## แหล่งข้อมูล

- `README.md`
- `PRODUCT.md`
- `src/subscription_intelligence/gmail_adapter/client.py`
- `src/subscription_intelligence/`
- `tests/test_extractors.py`
