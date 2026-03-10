import sqlite3

conn = sqlite3.connect('money_machine.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT slug, title, length(content) as clen, substr(content, -150) as endcontent, content FROM news_articles WHERE title LIKE '%Panduan Lengkap Memilih Tablet Terbaik%'")
row = cursor.fetchone()
if row:
    print(f"SLUG: {row['slug']}")
    print(f"TITLE: {row['title']}")
    print(f"CONTENT LENGTH: {row['clen']}")
    html_str = row['content']
    # Check for unclosed tags by counting <div> vs </div>
    open_div = html_str.count("<div")
    close_div = html_str.count("</div>")
    print(f"<div count: {open_div}")
    print(f"</div> count: {close_div}")
    
    open_p = html_str.count("<p")
    close_p = html_str.count("</p>")
    print(f"<p count: {open_p}")
    print(f"</p> count: {close_p}")

    open_ul = html_str.count("<ul")
    close_ul = html_str.count("</ul>")
    print(f"<ul count: {open_ul}")
    print(f"</ul> count: {close_ul}")

    open_li = html_str.count("<li")
    close_li = html_str.count("</li>")
    print(f"<li count: {open_li}")
    print(f"</li> count: {close_li}")

    open_h2 = html_str.count("<h2")
    close_h2 = html_str.count("</h2>")
    print(f"<h2 count: {open_h2}")
    print(f"</h2> count: {close_h2}")
else:
    print("Article not found!")

conn.close()
