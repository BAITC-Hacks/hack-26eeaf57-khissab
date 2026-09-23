# Career Quest — ishga tushirish va himoya qo‘llanmasi

[Asosiy README](../README.md) · [Texnik tekshiruvlar](../VERIFICATION.md)

Career Quest xodimning ko‘nikmalari, maqsad darajasi va o‘qish tarixidan kelib chiqib, 1–3 ta mos rivojlanish faoliyatini tavsiya qiladi. Tanlovni aniq formulali engine bajaradi; AI tayyor raqamlar asosida izoh beradi. API kalitisiz ham loyiha to‘liq ishlaydi.

## Noldan ishga tushirish

1. Docker Desktop yoki Docker Engine’ni ishga tushiring. `docker info` ishlashi va `docker compose version` kamida 2.24 bo‘lishi kerak.
2. Reponi yuklab oling:

   ```bash
   git clone https://github.com/BAITC-Hacks/hack-26eeaf57-khissab.git
   cd hack-26eeaf57-khissab
   mkdir -p data
   ```

3. Berilgan datasetning `career_quest_dataset/` ichidagi fayllarini `data/`ga ko‘chiring. `employees.json`, `events.json`, `skills.json` va `activity_history.csv` bevosita `data/` ichida bo‘lsin. Dataset Git’ga kiritilmaydi; uni alohida olish kerak.
4. Repo papkasida bitta buyruqni bajaring:

   ```bash
   docker compose up
   ```

5. [localhost:5173](http://localhost:5173) ni oching. **Try employee view** — xodim, **Try HR workspace** — HR paneli. `.env`, API kaliti va akkaunt yaratish shart emas. Birinchi build uchun internet yoki oldindan keshlangan dependency’lar zarur.

Backend holati: [localhost:8000/health](http://localhost:8000/health) → `{"status":"ok"}`. `docker compose ps` ikkala servis uchun `healthy` ko‘rsatishi kerak.

## Internet bo‘lmagan joyda

Internet bor paytda, namoyish kompyuterining arxitekturasiga mos muhitda:

```bash
bash scripts/prepare-offline.sh
```

Repo, `data/` va yaratilgan `offline/career-quest-images.tar` faylini birga olib boring. Offline kompyuterda Docker ishlayotgan bo‘lsin:

```bash
bash scripts/run-offline.sh
```

Bu rejim modelga so‘rov yubormaydi, image yuklab olish yoki build qilishga urinmaydi. Izohlar engine raqamlaridan shablon orqali hosil bo‘ladi. Windows’da Bash skriptlarini WSL orqali bajaring.

## 5 daqiqalik himoya ssenariysi

Quyidagi raqamlar yangi bazaga tegishli. Avval bajarilgan faoliyatlar natijani o‘zgartiradi.

| Vaqt | Ko‘rsatish | Asosiy fikr |
|---|---|---|
| 0:00–0:30 | Kirish sahifasi | “Biz umumiy kurs ro‘yxatini emas, xodimning maqsadiga mos keyingi qadamni ko‘rsatamiz.” |
| 0:30–1:30 | **Try employee view**, E0002 | Middle → Senior; maqsad ko‘nikmalari qamrovi **62%**. Bu lavozimga avtomatik ko‘tarilish ehtimoli emas. |
| 1:30–2:30 | System Design Fundamentals → **Why this fits you** | Benefit **6** × engagement **0.468** = score **2.808**. Maqsad, skill gap va tarix — kamida uch omil. AI tanlamaydi. |
| 2:30–3:00 | **Mark complete**, keyin sahifani yangilash | System Design va API Design **1 → 2**, qamrov **62% → 66%**. Natija saqlanadi; yangi faoliyatlar ochiladi. |
| 3:00–4:00 | Chiqish → **Try HR workspace** | Ko‘nikma kamchiliklari, faoliyatlar bo‘yicha qatnashish va keyingi qadami yo‘q xodimlar. Dastlabki bazada bunday xodimlar **34 ta**. |
| 4:00–5:00 | **Upload profiles → Files** | Quyidagi trap profilni yuklang. Qo‘shimcha hakam ma’lumotlari ham shu schema orqali qabul qilinadi. |

## Trap profilni yuklash

HR panelida **Upload profiles → Files** orqali ikkala faylni tanlang:

- [trap_employees.json](../examples/trap_employees.json)
- [trap_activity_history.csv](../examples/trap_activity_history.csv)

**Upload and open** bosing. Natija: **1 profil + 3 tarix yozuvi**. `DEMO_TRAP` uchun EV_005 birinchi: benefit **6**, engagement **1**, score **6**. Application Security past bo‘lsa ham, uchta workshop skip sabab EV_011 balli **0.216** bo‘ladi. Demak, eng past ko‘nikmani ko‘r-ko‘rona tanlash yo‘q.

Bu upload namunasi Application Security’dan foydalanadi. Talabdagi **Public Speaking vs System Design** holati alohida unit testda bor; tarixni yoki critical weighting’ni olib tashlash xatoni qayta yuzaga chiqaradi:

```bash
docker compose run --rm --no-deps backend python -m pytest backend/tests/test_engine.py -q -k adversarial
```

Bir xil profilni qayta yuklash `409` qaytaradi. Bu takroriy ID’dan himoya. Sahifani yangilash bazani tozalamaydi; oldindan namoyish qilingan profilning natijalari saqlanadi. Asosiy README’da [API orqali upload](../README.md#upload-and-test-a-trap-profile) ham ko‘rsatilgan.

## Tekshiruv va boshqaruv

```bash
docker compose ps
docker compose logs --tail=100 backend frontend
```

Backend testlari, mavjud local progress’ni o‘zgartirmasdan:

```bash
docker compose run --rm --no-deps -v "$PWD/examples:/app/examples:ro" \
  backend python -m pytest backend/tests -q
```

Frontend testlari va build:

```bash
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run build
```

To‘xtatish: `docker compose stop`. Qayta ochish: `docker compose up -d --wait`. Ma’lumotlar `storage/`da saqlanadi; oddiy restart uchun uni o‘chirmang.

## Kirish va model sozlamalari

Lokal demo rejimida ilovaga kira olgan har kim HR paneliga ham kira oladi. Bu sintetik ma’lumotli himoya uchun. Maxsus akkaunt orqali kirish, xodim/HR ruxsatlari va demo rejimini o‘chirish [README’da](../README.md#jury-access-and-private-sign-in) tushuntirilgan.

OpenAI majburiy emas. Uni yoqish uchun [model sozlash bo‘limi](../README.md#openai-and-local-explanations)ga qarang. API kalitini faqat lokal `.env`ga yozing. `.env`, dataset, SQLite bazasi va auth kalitini Git’ga qo‘shmang.

Xatolik bo‘lsa: [Troubleshooting](../README.md#troubleshooting). Baholash mezonlari va dalillar: [Verification](../README.md#verification). Yakuniy ballni hakamlar belgilaydi; README tekshiriladigan imkoniyatlarni ko‘rsatadi.
