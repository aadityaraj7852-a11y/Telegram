# 🎯 Telegram Quiz Bot (Hindi Guide)

Group me 20-question (ya jitne chaho) quiz karwane wala bot — Telegram
ke native Quiz Poll pe based, jisse anti-cheating built-in hai (koi
2 baar answer nahi de sakta, sahi answer time khatam hone tak hidden
rehta hai).

---

## ✨ Features (50+)

**Quiz System**
1. Group me `/quiz` se quiz shuru
2. Subject select karo
3. Chapter select karo (ya poora subject)
4. Question count choose karo (10/20/30)
5. Har question ka timer (default 20 sec, `.env` me change kar sakte ho)
6. Native Telegram Quiz Poll (anti-cheat built-in)
7. Options auto-shuffle nahi hote but questions random order me aate hain
8. Negative marking support (database level, easily enable ho sakta hai)
9. `/stopquiz` se beech me quiz rok sakte ho
10. Quiz khatam hone par auto leaderboard message

**Earning System**
11. Sahi jawab pe coins
12. Speed bonus (5 second ke andar jawab do to extra coins)
13. Referral system — dost ko invite karo, coins kamao
14. `/wallet` se balance dekho
15. `/withdraw` se withdrawal request bhejo
16. Admin withdrawal approve/reject kar sakta hai (reject pe auto refund)

**Leaderboard**
17. `/leaderboard` — top 10
18. `/globaltop` — top 20 global
19. Har quiz ke baad group-specific results

**Scorecard & History**
20. `/myscore` — overall stats
21. `/history` — last 10 quiz attempts
22. Per-user accuracy %, correct/wrong count

**Question Bank**
23. Manual add (`/addquestion` — step by step conversation)
24. Word (.docx) file se bulk upload (`/uploadword`)
25. `/samplefile` — sample format file milegi
26. `/exportquestions` — poora bank docx me export
27. `/deletequestion <id>` — question delete
28. Subject → Chapter hierarchy
29. `/subjects` — list dekho

**Admin Panel**
30. `/addadmin` / `/removeadmin` (owner only)
31. `/listadmins`
32. `/broadcast` — sab users ko message
33. `/postad` — group/channel me ad post (text + button + link)
34. `/backup` — database file download
35. `/restore` — backup se restore
36. `/stats` — bot ke overall stats
37. `/userinfo <id>` — kisi bhi user ka pura data (join date, last online, quizzes, coins)
38. `/ban` / `/unban`
39. `/withdrawals` — pending requests approve/reject
40. `/setcoinrate` — coin rate change

**User Tracking**
41. Joined date (bot kab on kiya)
42. Last seen / last online
43. Group join tracking
44. Total quizzes + questions attempted
45. Per-question answer log (kaunsa answer diya, kitne second me)

**Anti-Cheating**
46. Native Telegram quiz poll — ek user ek hi baar vote kar sakta hai
47. `is_anonymous=False` se pata chalta hai kisne kya diya
48. Answer sirf poll close hone tak hidden
49. Non-admin document upload ignore hota hai (spam file se DB corrupt nahi hoga)
50. Auto session lock — ek group me ek waqt sirf ek quiz chal sakta hai

**Extra**
51. Groups/channels tracking (ads/quiz bhejne ke liye)
52. SQLite WAL mode (fast, concurrent safe)
53. `.env` based config (token kahi hardcode nahi)

---

## 🚀 Setup Steps

### 1. Bot Token lo
- Telegram me [@BotFather](https://t.me/BotFather) kholo
- `/newbot` bhejo, naam do
- Jo token mile wo copy karo

### 2. Apna Telegram ID pata karo
- [@userinfobot](https://t.me/userinfobot) ko message karo, wo tumhara numeric ID dega — ye `OWNER_ID` banega

### 3. Bot ki Privacy Mode band karo (zaroori!)
- BotFather me jao → `/mybots` → apna bot chuno → `Bot Settings` → `Group Privacy` → **Turn off**
- Isse bot group ke saare messages (poll answers ke liye zaroori) padh payega

### 4. GitHub pe upload karo
```bash
git init
git add .
git commit -m "Telegram quiz bot"
git branch -M main
git remote add origin <tumhari-github-repo-url>
git push -u origin main
```

### 5. Render pe deploy karo
1. [render.com](https://render.com) pe account banao
2. **New +** → **Blueprint** → apni GitHub repo select karo (ye `render.yaml` khud padh lega)
   - Agar Blueprint na dikhe to **New +** → **Background Worker** manually banao, build command `pip install -r requirements.txt`, start command `python main.py`
3. Environment variables set karo:
   - `BOT_TOKEN` = apna token
   - `OWNER_ID` = apna numeric ID
   - (baaki defaults theek hain)
4. Deploy karo — logs me "Bot start ho raha hai..." dikhega

### 6. Bot ko test karo
- Bot ko apne group me add karo, **admin banao**
- Group me `/start` bhejo
- Admin/Owner ho to `/addquestion` ya `/uploadword` se questions daalo
- `/quiz` se test shuru karo

---

## 📄 Word File Format (Questions ke liye)

```
Subject: Physics
Chapter: Motion

Q1. Speed ka SI unit kya hai?
A) Kg
B) m/s
C) Newton
D) Watt
Answer: B
Explanation: Speed = distance/time hota hai.

Q2. Newton ka pehla niyam...
A) ...
B) ...
C) ...
D) ...
Answer: A
```

`/samplefile` command se ready-made example file bhi mil jayegi.

---

## ⚠️ Important Notes

- **Render Free Plan**: free background worker thoda so jata hai inactivity pe — agar bot down lage to Render dashboard check karo. Paid plan zyada reliable hoga.
- **Database persistence**: Render ka free disk ephemeral hota hai (redeploy pe reset ho sakta hai) — isiliye `/backup` command se regularly database download karke rakho. Agar chaho to Render ka **Persistent Disk** (paid) add karke `data/` folder ko mount kar sakte ho, taaki data kabhi na mite.
- Bot ko group me **admin** banana zaroori hai warna polls/messages sahi se kaam nahi karenge.

---

## 🗂 File Structure

```
quizbot/
├── main.py                 # Entry point, sab handlers register karta hai
├── config.py                # .env se settings load karta hai
├── database.py               # SQLite database — users, questions, sessions
├── quiz_engine.py            # Quiz poll logic, timer, scoring
├── requirements.txt
├── Procfile
├── render.yaml
├── .env.example
├── handlers/
│   ├── user_handlers.py     # /start /quiz /leaderboard etc.
│   └── admin_handlers.py    # /addquestion /broadcast /backup etc.
├── utils/
│   ├── docx_parser.py       # Word file se questions parse karta hai
│   ├── exporters.py          # docx export, scorecard/leaderboard text
│   └── permissions.py        # admin/owner check
└── data/                     # SQLite db yaha banti hai (runtime)
```

Koi feature aur chahiye ho (jaise image-based questions, weekly
tournaments, payment gateway integration) to bata dena, add kar
denge.
