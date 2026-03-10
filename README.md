# Overall Programs Dashboard

**Stable, Persistent Project Dashboard Manager**

## 🎯 Overview

This is a web-based dashboard application for managing multiple project programs. Unlike the auto-importing version, this application:
- ✅ **Starts with existing database** - No auto-import on startup
- ✅ **Manual Excel import** - Upload files only when needed via web interface
- ✅ **Persistent server** - Won't crash during code changes
- ✅ **Stable operation** - Debug mode always OFF for reliability
- ✅ **Independent database** - Separate from DashboardGeneratorWeb

## 🚀 Quick Start

### 1. Start the Server

**Double-click:** `START_SERVER_PERSISTENT.bat`

The server will:
- Install dependencies automatically
- Start on **http://localhost:5001**
- Open in persistent mode (no crashes)
- Keep running until you press Ctrl+C

### 2. Access the Dashboard

Open your browser to: **http://localhost:5001**

## 📊 Key Features

### Manual Project Import
- Click **"📁 Import New Project from Excel"** button on home page
- Select any .xlsx file from your computer
- File is imported immediately
- Page refreshes to show new project

### All Standard Features
- ✅ View all projects
- ✅ Edit tasks (inline and modal)
- ✅ Add new tasks
- ✅ Delete tasks
- ✅ Sort and filter
- ✅ Gantt chart visualization
- ✅ Critical path tracking
- ✅ Gate deadline management
- ✅ Gate change history and undo
- ✅ Export to Excel
- ✅ Export to HTML

## 🔄 Workflow

### First Time Use
1. Start server
2. Open http://localhost:5001 (will show empty - no projects yet)
3. Click "📁 Import New Project from Excel"
4. Select your first project Excel file
5. Project appears in the list
6. Click project to view dashboard

### Adding More Projects
1. Click "📁 Import New Project from Excel" button
2. Select another Excel file
3. New project is added to the list

### Daily Use
1. Start server (if not already running)
2. Open http://localhost:5001
3. Click any project to view/edit
4. All changes save to database automatically
5. Export to Excel anytime for backup

## 📁 File Structure

```
Overall programs dashboard/
├── server.py                     # Main Flask application
├── config.py                     # Configuration settings
├── database_manager.py           # Database operations
├── excel_parser.py               # Excel file parsing
├── excel_exporter.py             # Excel file generation
├── requirements.txt              # Python dependencies
├── START_SERVER_PERSISTENT.bat  # Server startup script
├── database/
│   └── dashboards.db            # SQLite database
├── templates/
│   ├── index.html               # Project list page (with import button)
│   └── dashboard.html           # Project dashboard page
├── exports/
│   └── [exported Excel files]   # Generated on export
└── README.md                    # This file
```

## ⚙️ Configuration

Edit `config.py` to change:

```python
SERVER_PORT = 5001              # Port number
DEBUG_MODE = False              # Always False for stability
DATABASE_PATH = 'database/dashboards.db'
EXCEL_OUTPUT_FOLDER = 'exports'
```

## 🛑 Stopping the Server

Press **Ctrl+C** in the server window

## 🔧 Troubleshooting

### Port Already in Use
```powershell
# Find process on port 5001
netstat -ano | findstr :5001

# Kill the process (replace PID with actual number)
Stop-Process -Id <PID>
```

### Server Won't Start
1. Check Python is installed: `python --version`
2. Check port 5001 is available
3. Try restarting your computer

### Excel Import Fails
1. Ensure file is .xlsx format (not .xls)
2. Check file follows correct format:
   - Row 3, Column C: Project Name
   - Row 5, Column C: Manager Name
   - Row 10: Headers
   - Row 11+: Task data
3. File should not be open in Excel

### Database Issues
Delete `database/dashboards.db` and restart server to recreate fresh database.

## 📊 Excel File Format

Your Excel file should have:

**Row 3, Column C:** Project Name  
**Row 5, Column C:** Manager Name  
**Row 10:** Headers (Ref ID, Name, Phase, Owner, Start, Status, End, Closed, Result)  
**Row 11+:** Task data

**Column Mapping:**
- A: Reference ID
- B: Task Name
- C: Phase
- D: Owner
- E: Start Date
- F: Status
- G: End Date
- H: Date Closed
- I: Result

## 🔐 Security Notes

- Server runs on localhost only (127.0.0.1)
- No authentication (local use only)
- For production: Add authentication and HTTPS

## 🆚 Differences from DashboardGeneratorWeb

| Feature | DashboardGeneratorWeb | Overall Programs Dashboard |
|---------|----------------------|---------------------------|
| **Excel Import** | Automatic (every 10 seconds) | Manual (button click) |
| **Startup** | Auto-imports from folder | Loads from existing database |
| **Port** | 5000 | 5001 |
| **Database** | Shared | Independent |
| **Server Mode** | Can crash during edits | Persistent (stable) |
| **File Location** | Watches specific folder | Upload from anywhere |

## 💡 Best Practices

1. **Keep server running** - Don't close the window while using
2. **Export regularly** - Backup your data to Excel weekly
3. **Import once** - Each Excel file imports once, then edit in dashboard
4. **Bookmark URL** - http://localhost:5001 for quick access
5. **Use persistent mode** - Prevents crashes during development

## 📝 Version Info

- **Port:** 5001
- **Database:** Independent
- **Mode:** Persistent (Stable)
- **Import:** Manual via web interface

## 🎉 Ready to Use!

1. Double-click `START_SERVER_PERSISTENT.bat`
2. Open http://localhost:5001
3. Import your first project
4. Start managing your dashboards!

---

**Questions or Issues?**
- Check this README
- Check server console for error messages
- Verify Excel file format
- Try restarting server
