"""
Unified server — Dashboard + Portal on port 5003
/ → /portal
/dashboard/... → Dashboard app
/portal/... → Portal app
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from flask import Flask, redirect
import config

from server import register_dashboard
from portal.routes import register_portal

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'unified-portal-dashboard-2026'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
app.config['TEMPLATES_AUTO_RELOAD'] = True

register_dashboard(app)
register_portal(app)

@app.after_request
def no_cache(response):
    from flask import request
    if request.method == 'GET':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.route('/')
def root():
    return redirect('/portal')

if __name__ == '__main__':
    print('=' * 50)
    print('  Unified Server (Dashboard + Portal)')
    print(f'  http://localhost:{config.SERVER_PORT}')
    print(f'  Dashboard: http://localhost:{config.SERVER_PORT}/dashboard')
    print(f'  Portal:    http://localhost:{config.SERVER_PORT}/portal')
    print('=' * 50)
    app.run(host='127.0.0.1', port=config.SERVER_PORT, debug=False)
