# 🚀 Quick Start - Overall Programs Dashboard

## ✅ Installation Complete!

Everything is ready to use. Here's how to start:

---

## Step 1: Start the Server

### Option A: Desktop Shortcut (Easiest)
Double-click the shortcut on your Desktop:
```
"Overall Programs Dashboard"
```

### Option B: Double-Click Batch File
Navigate to folder and double-click:
```
START_SERVER_PERSISTENT.bat
```

### Option C: Command Line
```powershell
cd "C:\Users\omalevsky\OneDrive - Emerson\Documents\AI Projects\Overall programs dashboard"
.\START_SERVER_PERSISTENT.bat
```

---

## Step 2: Open Your Browser

The server will start on:
**http://localhost:5001**

Your browser should open automatically. If not, open it manually.

---

## Step 3: Import Your First Project

1. You'll see an empty dashboard (no projects yet)
2. Click the big **"📁 Import New Project from Excel"** button
3. Browse to select your Excel file (.xlsx)
4. Wait for import to complete (progress indicator shows)
5. Page refreshes automatically
6. Your project appears in the list!

---

## 🎯 Daily Workflow

### Starting Work
1. Double-click Desktop shortcut
2. Browser opens to http://localhost:5001
3. Click any project to view/edit

### Adding Projects
1. Click "📁 Import New Project from Excel"
2. Select .xlsx file from anywhere on your computer
3. New project appears in list

### Editing Tasks
1. Open project dashboard
2. Click dates, status, or Edit button
3. Changes save automatically to database

### Exporting Data
1. Open project dashboard
2. Click "📊 Export to Excel" button
3. File downloads with timestamp

---

## 🔍 What to Expect

### First Time (Empty Database)
```
┌─────────────────────────────────────┐
│  Overall Programs Dashboard         │
│                                     │
│  [📁 Import New Project from Excel] │  ← Click this!
│                                     │
│  No projects yet.                   │
│  Import your first project above!   │
└─────────────────────────────────────┘
```

### After Importing Projects
```
┌─────────────────────────────────────┐
│  Overall Programs Dashboard         │
│                                     │
│  [📁 Import New Project from Excel] │
│                                     │
│  📋 Your Projects (3)               │
│  ┌─────────────────────────────┐   │
│  │ Saturn Project              │   │
│  │ 77 tasks | Olga Malevsky    │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ Nevada Nano Sensor          │   │
│  │ 61 tasks | John Smith       │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

## 💡 Key Differences from Old Version

| Old (DashboardGeneratorWeb) | New (Overall Programs) |
|----------------------------|------------------------|
| Auto-imports from folder every 10s | Manual import via button |
| Port 5000 | Port 5001 |
| Shared database | Independent database |
| Can crash during edits | Persistent (stable) |

---

## 🛑 Stopping the Server

In the server window, press: **Ctrl+C**

---

## ❓ Common Questions

**Q: Where is my data stored?**
A: In `database/dashboards.db` (SQLite database)

**Q: Can I import the same Excel file twice?**
A: Yes, it will update the existing project with new data

**Q: What if I accidentally close the server?**
A: Just start it again. Your data is safe in the database.

**Q: Can I run both dashboards at the same time?**
A: Yes! Old one runs on port 5000, new one on port 5001

**Q: How do I backup my data?**
A: Export each project to Excel, or copy the entire `database` folder

---

## 🎉 You're Ready!

1. ✅ Server installed
2. ✅ Desktop shortcut created
3. ✅ Dependencies installed
4. ✅ Database ready

**Next step:** Double-click the Desktop shortcut and import your first project!

---

## 🆘 Need Help?

- Read `README.md` for detailed documentation
- Check server window for error messages
- Verify Excel file format (see README.md)
- Try restarting server

---

**Server URL:** http://localhost:5001  
**Port:** 5001  
**Mode:** Persistent (Stable)  
**Database:** Independent from DashboardGeneratorWeb
