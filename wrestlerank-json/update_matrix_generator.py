import os
import re

def update_matrix_generator():
    """Update the matrix generator to make cells square and fix header row."""
    # Path to the matrix generator
    current_dir = os.path.dirname(os.path.abspath(__file__))
    matrix_generator_path = os.path.join(current_dir, 'wrestlerank', 'matrix', 'matrix_generator.py')
    
    if not os.path.exists(matrix_generator_path):
        # Try the parent directory
        parent_dir = os.path.dirname(current_dir)
        matrix_generator_path = os.path.join(parent_dir, 'wrestlerank', 'matrix', 'matrix_generator.py')
        
        if not os.path.exists(matrix_generator_path):
            print(f"Error: matrix_generator.py not found")
            return
    
    print(f"Updating {matrix_generator_path}...")
    
    try:
        with open(matrix_generator_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # CSS to add
        css_fixes = """
        /* Make relationship cells square */
        #matrix-table td.relationship-cell {
            width: 40px;
            height: 40px;
            min-width: 40px;
            min-height: 40px;
            max-width: 40px;
            max-height: 40px;
            text-align: center;
            vertical-align: middle;
        }
        
        /* Fix header row to stay on top when scrolling */
        #matrix-table {
            position: relative;
        }
        
        #matrix-table thead {
            position: sticky;
            top: 0;
            z-index: 10;
            background-color: white;
        }
        
        #matrix-table th.wrestler-header, 
        #matrix-table th.rank-header {
            position: sticky;
            top: 0;
            z-index: 20;
            background-color: white;
        }
        
        /* Add some spacing and borders for better readability */
        #matrix-table {
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid #ddd;
        }
        
        #matrix-table th, 
        #matrix-table td {
            border: 1px solid #ddd;
            padding: 8px;
        }
        
        /* Highlight diagonal cells */
        #matrix-table td.diagonal-cell {
            background-color: #f2f2f2;
        }
        """
        
        # Change this line in the CSS:
        css_fixes = css_fixes.replace(
            ".matrix-table",
            "#matrix-table"
        )
        
        # Check if we need to add CSS
        if "Make relationship cells square" not in content:
            # Look for the style section
            style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
            if style_match:
                # Add to existing style section
                style_content = style_match.group(1)
                new_style = f"{style_content}\n{css_fixes}"
                content = content.replace(style_match.group(0), f"<style>{new_style}</style>")
                print("Added CSS to existing style section")
            else:
                # Look for </head> tag
                if "</head>" in content:
                    content = content.replace("</head>", f"<style>{css_fixes}</style></head>")
                    print("Added CSS before </head>")
                else:
                    # Look for the HTML template
                    html_template_match = re.search(r'html_template\s*=\s*[\'"]([^\'"]+)[\'"]', content)
                    if html_template_match:
                        # Replace the HTML template
                        html_template = html_template_match.group(1)
                        if "</head>" in html_template:
                            new_html_template = html_template.replace("</head>", f"<style>{css_fixes}</style></head>")
                            content = content.replace(html_template, new_html_template)
                            print("Added CSS to HTML template")
                        else:
                            # Insert after <html>
                            new_html_template = html_template.replace("<html>", f"<html><head><style>{css_fixes}</style></head>")
                            content = content.replace(html_template, new_html_template)
                            print("Added CSS after <html> in HTML template")
                    else:
                        # Look for a string that contains <table
                        table_match = re.search(r'[\'"]([^\'"]*<table[^\'"]*)[\'"]', content)
                        if table_match:
                            table_html = table_match.group(1)
                            new_table_html = f"<style>{css_fixes}</style>{table_html}"
                            content = content.replace(table_html, new_table_html)
                            print("Added CSS before table HTML")
                        else:
                            print("Could not find a suitable place to add CSS")
        
        # Add classes to table elements
        if "relationship-cell" not in content:
            # Look for the HTML that generates the table
            # This is a bit tricky because it depends on how the HTML is generated
            
            # First, try to find a template string with <td data-wrestler1-id
            td_match = re.search(r'[\'"]([^\'"]*<td[^>]*data-wrestler1-id[^\'"]*)[\'"]', content)
            if td_match:
                td_html = td_match.group(1)
                new_td_html = td_html.replace("<td", '<td class="relationship-cell"')
                content = content.replace(td_html, new_td_html)
                print("Added class to relationship cells")
            
            # Look for <th>Wrestler</th>
            wrestler_th_match = re.search(r'[\'"]([^\'"]*<th[^>]*>Wrestler</th>[^\'"]*)[\'"]', content)
            if wrestler_th_match:
                wrestler_th_html = wrestler_th_match.group(1)
                new_wrestler_th_html = wrestler_th_html.replace("<th", '<th class="wrestler-header"')
                content = content.replace(wrestler_th_html, new_wrestler_th_html)
                print("Added class to wrestler header cell")
            
            # Look for <th>Rank</th>
            rank_th_match = re.search(r'[\'"]([^\'"]*<th[^>]*>Rank</th>[^\'"]*)[\'"]', content)
            if rank_th_match:
                rank_th_html = rank_th_match.group(1)
                new_rank_th_html = rank_th_html.replace("<th", '<th class="rank-header"')
                content = content.replace(rank_th_html, new_rank_th_html)
                print("Added class to rank header cell")
            
            # Add class to diagonal cells - this is more complex
            # We need to find where the table cells are generated
            # Look for code that checks if wrestler1_id == wrestler2_id
            diagonal_match = re.search(r'if\s+wrestler1_id\s*==\s*wrestler2_id', content)
            if diagonal_match:
                # Find the line that generates the TD tag
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if diagonal_match.group(0) in line:
                        # Look for the TD tag in the next few lines
                        for j in range(i, min(i + 10, len(lines))):
                            if '<td' in lines[j]:
                                if 'class=' in lines[j]:
                                    lines[j] = lines[j].replace('class="', 'class="diagonal-cell ')
                                else:
                                    lines[j] = lines[j].replace('<td', '<td class="diagonal-cell"')
                                print("Added class to diagonal cells")
                                break
                        break
                content = '\n'.join(lines)
        
        # Write the updated content back to the file
        with open(matrix_generator_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Successfully updated {matrix_generator_path}")
        
    except Exception as e:
        print(f"Error updating matrix generator: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nAll done! Try generating a matrix again:")
    print("  .\\run.ps1 matrix 106")

if __name__ == "__main__":
    update_matrix_generator() 