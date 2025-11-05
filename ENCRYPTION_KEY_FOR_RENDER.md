# 🔑 ENCRYPTION_KEY for Render

**Generated:** 2025-11-05  
**Purpose:** Encrypt admin credentials in admin_credentials table

---

## Your Encryption Key

```
srRkN-3FU55UK07QCr-25vHK4nZvAGCD22kjTwtCb1Y=
```

⚠️ **Keep this secure! Do not share publicly.**

---

## How to Add to Render

### Step-by-Step:

1. **Go to Render Dashboard**
   - URL: https://dashboard.render.com
   - Select your Kopkad FastAPI service

2. **Navigate to Environment Variables**
   - Click "Environment" in the left sidebar
   - Or go to Settings → Environment

3. **Add the Variable**
   - Click "Add Environment Variable"
   - **Key:** `ENCRYPTION_KEY`
   - **Value:** `srRkN-3FU55UK07QCr-25vHK4nZvAGCD22kjTwtCb1Y=`
   - Click "Save Changes"

4. **Redeploy**
   - Render will automatically redeploy your service
   - Or manually click "Manual Deploy" → "Deploy latest commit"

---

## Verification

### Before Adding Key (Warning in logs):
```
WARNING:utils.password_utils:No ENCRYPTION_KEY in settings - using generated key (will change on restart!)
```

### After Adding Key (No warning):
The warning should disappear from your logs completely.

---

## Testing Admin Credentials

After adding the key:

1. **Create a new business** (as agent/super_admin)
2. **Check admin credentials** (as super_admin)
   - Navigate to: `/dashboard/admin-credentials`
   - You should see the decrypted password and PIN
   - No `[DECRYPTION ERROR]` messages

3. **Verify consistency**
   - Restart the service
   - Check credentials again
   - Should still decrypt correctly

---

## What This Key Does

- **Encrypts:** Temporary admin passwords when businesses are created
- **Decrypts:** Passwords when super_admin views them in Admin Credentials page
- **Protects:** Admin credentials in the database (stored encrypted)

**Without this key:**
- A new random key is generated on each restart
- Previously encrypted passwords cannot be decrypted
- Admin credentials become inaccessible

**With this key:**
- Same key used across all restarts
- Encrypted passwords can always be decrypted
- Admin credentials remain accessible

---

## Security Best Practices

1. ✅ **Store securely**
   - Save in password manager
   - Keep in secure notes
   - Do not commit to git

2. ✅ **Limit access**
   - Only share with trusted team members
   - Render encrypts environment variables by default

3. ✅ **Rotate if compromised**
   - Generate new key
   - Update in Render
   - Note: Old encrypted passwords won't decrypt with new key

4. ✅ **Backup**
   - Save this key somewhere safe
   - If lost, encrypted passwords are unrecoverable

---

## Troubleshooting

### Warning Still Appears

**Checklist:**
- [ ] Key added exactly as shown (no extra spaces)
- [ ] Environment variable name is exactly `ENCRYPTION_KEY`
- [ ] Service has been redeployed
- [ ] Check Deploy Logs to confirm it loaded

### Cannot Decrypt Passwords

**Possible causes:**
- Different key than when passwords were encrypted
- Key was changed after encryption
- Typo in the key value

**Solution:**
- Use the same key consistently
- If you must change it, you'll need to re-encrypt all passwords

---

## Your Exact Configuration

**Environment Variable Name (Render):**
```
ENCRYPTION_KEY
```

**Environment Variable Value (Render):**
```
srRkN-3FU55UK07QCr-25vHK4nZvAGCD22kjTwtCb1Y=
```

**That's it!** Just copy-paste these into Render.

---

## After Adding

Once added and deployed, you should see in your app logs:
- No more warnings about encryption key
- Admin credentials encrypt/decrypt properly
- System works consistently across restarts

---

**Last Updated:** 2025-11-05  
**Key Generated:** 2025-11-05  
**Status:** Ready to add to Render

