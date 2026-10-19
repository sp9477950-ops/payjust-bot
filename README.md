# Transparent Rewards & Referral Telegram Bot

Yeh bot **Pay Plus Bot** ki tarah referral, task, aur points mechanism par chalta hai, lekin **100% genuine, transparent aur clean code** ke sath.

---

## 🌟 Mukhya Features (Core Features)

1. **👥 Refer & Earn System:**
   - Har user ko unka personal invite link milta hai (`t.me/yourbot?start=USER_ID`).
   - Naye dosto ko jodne par user ke balance me turant Points credit hote hain aur referrer ko instant Telegram notification milta hai.
2. **🎁 24-Hour Daily Bonus:**
   - Har 24 ghante me user ek baar daily reward claim kar sakta hai.
3. **💰 Wallet & Balance:**
   - User apna current balance aur total referrals live dekh sakta hai.
4. **💳 Withdrawal System (Manual Admin Review):**
   - User apna UPI ID/Payment detail submit karke withdrawal request daal sakta hai.
   - Ye request seedha **Admin** ke Telegram par aati hai jisme `[Approve]` aur `[Reject]` ke buttons hote hain.
   - Payout approve hone par user ko instant update milta hai.
5. **🏆 Top Referrers Leaderboard:**
   - Sabse zyada invite karne wale top 5 users ki live ranking.
6. **📢 Mandatory Channels Verification (Optional):**
   - Agar aap apna channel promote karna chahte hain, toh bot automatically check karta hai ki user ne channel join kiya ya nahi.

---

## 🚀 Kaise Setup Aur Run Karein

### Step 1: Dependencies Install Karein
```bash
cd /Users/ottmk7/.gemini/antigravity-ide/scratch/telegram-rewards-bot
pip install -r requirements.txt
```

### Step 2: Settings Configure Karein (`config.py`)
[config.py](file:///Users/ottmk7/.gemini/antigravity-ide/scratch/telegram-rewards-bot/config.py) file kholein aur zaroorat ke anusaar badlav karein:
- `ADMIN_ID`: Apna Telegram numeric ID dalein (Apna ID janne ke liye Telegram par `@userinfobot` ko start karein).
- `POINTS_PER_REFERRAL`: Ek invite par kitne points dene hain (Default: 50).
- `MIN_WITHDRAWAL_POINTS`: Minimum withdrawal limit (Default: 100).
- `MANDATORY_CHANNELS`: Agar koi channel join karwana ho (e.g. `["@mychannel"]`).

### Step 3: Bot Start Karein
```bash
python bot.py
```
