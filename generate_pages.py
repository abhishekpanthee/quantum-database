import markdown
from bs4 import BeautifulSoup

def extract_toc(md_text):
    """Extracts the table of contents and formats it hierarchically with bullets and links."""
    html_content = markdown.markdown(md_text, extensions=['toc', 'fenced_code', 'tables'])
    soup = BeautifulSoup(html_content, 'html.parser')

    toc_items = []
    indent_levels = []
    
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # Skip the TOC header if it exists in the content
        header_text = header.get_text(strip=True).lower()
        if "table of contents" in header_text or "toc" in header_text:
            continue
            
        level = int(header.name[1])
        header_id = header_text.replace(' ', '-').replace("/", "-")
        header['id'] = header_id

        while indent_levels and indent_levels[-1] >= level:
            toc_items.append('</ul>')
            indent_levels.pop()

        toc_class = f"toc-level-{level}"
        bullet = "•" if level > 1 else "▸"
        toc_items.append(f'<li class="{toc_class}"><span class="toc-bullet">{bullet}</span><a href="#{header_id}">{header.get_text()}</a></li>')

        if not indent_levels or indent_levels[-1] < level:
            toc_items.insert(-1, '<ul>')
            indent_levels.append(level)

    while indent_levels:
        toc_items.append('</ul>')
        indent_levels.pop()
    
    return '\n'.join(toc_items), str(soup)

def generate_html(md_file, output_file):
    """Reads the markdown file, extracts the TOC, and generates an HTML file."""
    with open(md_file, 'r', encoding='utf-8') as f:
        md_text = f.read()
    
    toc_html, content_html = extract_toc(md_text)
    
    # Remove the original TOC from content
    content_soup = BeautifulSoup(content_html, 'html.parser')
    toc_section = content_soup.find(lambda tag: tag.name and tag.name.startswith('h') and 
                                  ("table of contents" in tag.get_text(strip=True).lower() or 
                                   "toc" in tag.get_text(strip=True).lower()))
    if toc_section:
        # Remove the TOC header and any content until next header
        for sibling in toc_section.find_next_siblings():
            if sibling.name and sibling.name.startswith('h'):
                break
            sibling.decompose()
        toc_section.decompose()
    
    cleaned_content = str(content_soup)
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
        <meta charset='UTF-8'>
        <meta name='viewport' content='width=device-width, initial-scale=1.0'>
        <title>Quantum Database</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
        <link rel="icon" type="image/png" href="https://res.cloudinary.com/dpwglhp5u/image/upload/v1743410324/favicon_yakhkw.ico">

        <style>
            :root {{
                --primary: #bb86fc;
                --primary-variant: #3700b3;
                --secondary: #03dac6;
                --background: #121212;
                --surface: #1e1e1e;
                --error: #cf6679;
                --on-primary: #000000;
                --on-secondary: #000000;
                --on-background: #e0e0e0;
                --on-surface: #e0e0e0;
                --on-error: #000000;
                --header-gradient: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            }}
            
            body {{
                display: flex;
                flex-direction: column;
                font-family: 'Roboto', sans-serif;
                margin: 0;
                background: var(--background);
                color: var(--on-background);
                line-height: 1.6;
                min-height: 100vh;
            }}
            
            header {{
                background: var(--header-gradient);
                color: white;
                padding: 0.6rem 1.5rem;
                text-align: center;
                font-size: 1.3rem;
                font-weight: bold;
                position: fixed;
                width: 100%;
                top: 0;
                z-index: 1000;
                box-shadow: 0 2px 10px rgba(0,0,0,0.3);
                font-family: 'Montserrat', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                height: 45px;
            }}
            
            footer {{
                background: var(--header-gradient);
                color: white;
                text-align: center;
                padding: 0.5rem;
                position: fixed;
                bottom: 0;
                width: 100%;
                font-size: 0.75rem;
                box-shadow: 0 -2px 10px rgba(0,0,0,0.3);
                height: 35px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            
            #sidebar {{
                width: 280px;
                padding: 1.2rem;
                background: var(--surface);
                color: white;
                height: calc(100vh - 80px);
                overflow-y: auto;
                position: fixed;
                top: 45px;
                box-shadow: 2px 0 5px rgba(0,0,0,0.2);
            }}
                        
            #sidebar::-webkit-scrollbar {{
                width: 8px;
            }}

            #sidebar::-webkit-scrollbar-thumb {{
                background: linear-gradient(180deg, #000000, #333333);
                border-radius: 4px;
            }}

            #sidebar::-webkit-scrollbar-track {{
                background: #121212;
            }}

        
            #sidebar {{
                scrollbar-width: thin;
                scrollbar-color: #333333 #121212;
            }}

            
            #main-container {{
                display: flex;
                margin-top: 45px;
                margin-bottom: 35px;
                min-height: calc(100vh - 80px);
            }}
            
            #content {{
                margin-left: 350px;
                padding: 2rem 3rem;
                flex-grow: 1;
                width: calc(100% - 280px);
                max-width: none;
                margin-right: 250px;
                margin-top: 10px;
            }}
            
            /* Heading Styles */
            h1 {{
                text-align: center;
                color: var(--primary);
                font-size: 2.4rem;
                margin: 1.5rem 0 2rem 0;
                font-family: 'Montserrat', sans-serif;
                position: relative;
                padding-bottom: 1rem;
                font-weight: 700;
            }}
            
            h1:after {{
                content: "";
                position: absolute;
                bottom: 0;
                left: 50%;
                transform: translateX(-50%);
                width: 120px;
                height: 4px;
                background: var(--secondary);
                border-radius: 2px;
            }}
            
            h2 {{
                text-align: center;
                color: var(--primary);
                font-size: 1.9rem;
                margin: 2.5rem 0 1.5rem 0;
                font-family: 'Montserrat', sans-serif;
                font-weight: 600;
                border-bottom: 2px solid var(--primary-variant);
                padding-bottom: 0.5rem;
                display: inline-block;
                width: 100%;
            }}
            
            h3 {{
                color: var(--secondary);
                font-size: 1.5rem;
                margin: 2rem 0 1rem 0;
                font-family: 'Montserrat', sans-serif;
                font-weight: 600;
                padding-left: 0.5rem;
                border-left: 4px solid var(--secondary);
            }}
            
            h4 {{
                color: var(--primary);
                font-size: 1.3rem;
                margin: 1.5rem 0 0.8rem 0;
                font-family: 'Montserrat', sans-serif;
            }}
            
            h5, h6 {{
                color: var(--primary);
                font-size: 1.1rem;
                margin: 1.2rem 0 0.6rem 0;
                font-family: 'Montserrat', sans-serif;
            }}
            
            /* TOC Styles */
            #sidebar h2 {{
                color: var(--secondary);
                font-size: 1.2rem;
                margin-bottom: 1rem;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid var(--secondary);
                border-left: none;
                text-align: left;
            }}
            #sidebar ul {{
                list-style-type: none;
                padding-left: 0;
                margin: 0;
            }}
            
            #sidebar ul ul {{
                padding-left: 1.2rem;
            }}
            
            #sidebar li {{
                margin-bottom: 0.4rem;
                position: relative;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
            }}
            
            .toc-bullet {{
                margin-right: 0.6rem;
                color: var(--primary);
                font-weight: bold;
                font-size: 1.1em;
            }}
            
            #sidebar li.toc-level-1 {{
                font-size: 1.1rem;
                font-weight: 600;
                margin: 0.8rem 0;
            }}
            
            #sidebar li.toc-level-2 {{
                font-size: 1rem;
                font-weight: 500;
                margin: 0.6rem 0 0.6rem 1rem;
            }}
            
            #sidebar li.toc-level-3 {{
                font-size: 0.95rem;
                margin: 0.5rem 0 0.5rem 2rem;
            }}
            
            #sidebar li.toc-level-4 {{
                font-size: 0.9rem;
                margin: 0.4rem 0 0.4rem 3rem;
            }}
            
            #sidebar li.toc-level-5,
            #sidebar li.toc-level-6 {{
                font-size: 0.85rem;
                margin: 0.3rem 0 0.3rem 4rem;
            }}
            
            #sidebar a {{
                text-decoration: none;
                color: var(--on-surface);
                transition: all 0.3s ease;
                display: block;
                padding: 0.1rem 0;
            }}
            
            #sidebar a:hover {{
                color: var(--primary);
                transform: translateX(5px);
            }}
            
            /* Content Styles */
            p, li {{
                font-size: 1.1rem;
                line-height: 1.7;
                color: var(--on-background);
                margin-bottom: 1.2rem;
            }}
            
            a {{
                color: var(--primary);
                transition: color 0.3s;
                font-weight: 500;
            }}
            
            a:hover {{
                color: var(--secondary);
                text-decoration: underline;
            }}
            
            pre {{
                background: #282c34;
                padding: 1.2rem;
                border-radius: 8px;
                overflow-x: auto;
                color: #e0e0e0;
                font-family: 'Courier New', monospace;
                margin: 1.5rem 0;
                box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
            }}
            
            /* Social Icons */
            .social-icons {{
                display: flex;
                justify-content: center;
                gap: 1rem;
                margin-bottom: 0.2rem;
            }}
            
            .social-icons a {{
                color: white;
                font-size: 1rem;
                transition: all 0.3s ease;
            }}
            
            .social-icons a:hover {{
                color: var(--secondary);
                transform: translateY(-2px);
                text-decoration: none;
            }}
            
            /* Responsive Design */
            @media (max-width: 992px) {{
                #sidebar {{
                    width: 250px;
                }}
                #content {{
                    margin-left: 250px;
                    padding: 1.5rem 2rem;
                }}
            }}
            
            @media (max-width: 768px) {{
                #sidebar {{
                    display: none;
                }}
                #content {{
                    margin-left: 0;
                    padding: 1.5rem;
                    width: 100%;
                }}
                
                header {{
                    font-size: 1.2rem;
                    height: 40px;
                }}
                
                footer {{
                    height: 30px;
                    font-size: 0.7rem;
                }}
                
                #main-container {{
                    margin-top: 40px;
                    margin-bottom: 30px;
                    min-height: calc(100vh - 70px);
                }}
            }}
        </style>
    </head>
    <body>
        <header>
            <i class="fas fa-database"></i>
            <span>Quantum Database </span>
        </header>
        <div id="main-container">
            <div id='sidebar'>
                <h2><i class="fas fa-list"></i> Table of Contents</h2>
                {toc_html}
            </div>
            <div id='content'>
                {cleaned_content}
            </div>
        </div>
        <footer>
            <div class='social-icons'>
                <a href='https://github.com/abhishekpanthee' target='_blank' title='GitHub'><i class="fab fa-github"></i></a>
                <a href='https://twitter.com/abhishepanthee' target='_blank' title='Twitter'><i class="fab fa-twitter"></i></a>
                <a href='https://linkedin.com/in/abhishekpanthee' target='_blank' title='LinkedIn'><i class="fab fa-linkedin"></i></a>
            </div>
            &copy; 2025 Codecrumbs404-Inc. All Rights Reserved.
        </footer>
    </body>
    </html>
    """
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print(f'HTML file generated: {output_file}')

# Example usage
generate_html('README.md', 'index.html')