PITCH&BREW V2 DEPLOYMENT

GITHUB PAGES:
Upload/replace index.html, style.css, script.js and data.json in the GitHub repository.

PYTHONANYWHERE:
Replace the existing app.py with this app.py, then click Reload.

The customer app uses the live API:
https://pitchandbrew.pythonanywhere.com/api/schedule

The included app.py enables CORS for GitHub Pages and initializes the database when loaded by WSGI.

Most customer-visible content is editable in data.json. Cafe items can be added/removed/renamed and prices changed there.
The weekly schedule remains controlled by the PythonAnywhere Admin Panel.
