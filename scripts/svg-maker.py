    #!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
from datetime import datetime
import xml.etree.ElementTree as ET
import re
import argparse
import readline

# Define the base class for product types
class ProductType:
    """Base class for all product types"""
    def __init__(self, filename):
        self.filename = filename
        self.parse_filename()
        
    def parse_filename(self):
        """Each subclass should implement its own parsing logic"""
        pass
        
    def create_file(self, project_dir):
        """Each subclass should implement its own file creation logic"""
        pass

# Define the SM product type class
class SM(ProductType):
    """Class for handling SM product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.name = ""
        self.size = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: sm-<name>-<size>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'sm' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.name = parts[1]  # Case sensitive
        self.size = parts[2].lower()  # Not case sensitive
        self.material = parts[3].lower()  # Not case sensitive
        
        # Validate size
        valid_sizes = ["small", "standard", "large"]
        if self.size not in valid_sizes:
            raise ValueError(f"Size must be one of {valid_sizes}, got '{self.size}'")
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Determine template file
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        template_file = os.path.join(template_dir, f"sm_{self.size}_template.svg")
        
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        # Using xpath-like search which ElementTree doesn't fully support
        # We'll need to iterate through elements
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            # This might need adjustment based on the actual structure of your SVG
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Circle product type class
class Circle(ProductType):
    """Class for handling Circle product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.age = ""
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: circle-<age>-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'circle' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.age = parts[1].lower()  # Not case sensitive
        self.name = parts[2].upper()  # CAPITALIZE the entire name
        self.material = parts[3].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Check for age-specific template first
        template_file = os.path.join(template_dir, f"circle-{self.age}-template.svg")
        
        # If age-specific template doesn't exist, use the OTHER template
        if not os.path.exists(template_file):
            # Fall back to OTHER template
            template_file = os.path.join(template_dir, "circle-OTHER-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Square product type class
class Square(ProductType):
    """Class for handling Square product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.age = ""
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: square-<age>-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'square' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.age = parts[1].lower()  # Not case sensitive
        self.name = parts[2].upper()  # CAPITALIZE the entire name
        self.material = parts[3].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Check for age-specific template first
        template_file = os.path.join(template_dir, f"square-{self.age}-template.svg")
        
        # If age-specific template doesn't exist, use the OTHER template
        if not os.path.exists(template_file):
            # Fall back to OTHER template
            template_file = os.path.join(template_dir, "square-OTHER-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the School product type class
class School(ProductType):
    """Class for handling School product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.font = ""
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: school-<font>-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'school' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.font = parts[1].lower()  # Not case sensitive
        self.name = parts[2]  # Case sensitive - store exactly as written
        self.material = parts[3].lower()  # Not case sensitive
        
        # Validate font
        valid_fonts = ["1", "2", "3", "4"]
        if self.font not in valid_fonts:
            raise ValueError(f"Font must be one of {valid_fonts}, got '{self.font}'")
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file based on font
        template_file = os.path.join(template_dir, f"school-{self.font}-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Cross product type class
class Cross(ProductType):
    """Class for handling Cross product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.name = ""
        self.size = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: cross-<name>-<size>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'cross' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.name = parts[1]  # Case sensitive
        self.size = parts[2].lower()  # Not case sensitive
        self.material = parts[3].lower()  # Not case sensitive
        
        # Validate size
        valid_sizes = ["small", "standard"]
        if self.size not in valid_sizes:
            raise ValueError(f"Size must be one of {valid_sizes}, got '{self.size}'")
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file based on size
        template_file = os.path.join(template_dir, f"cross_{self.size}_template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the GB product type class
class GB(ProductType):
    """Class for handling GB (God Bless) product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 2
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: gb-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'gb' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.name = parts[1]  # Case sensitive
        self.material = parts[2].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file
        template_file = os.path.join(template_dir, "god_bless_template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Sweet16 product type class
class Sweet16(ProductType):
    """Class for handling Sweet16 product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 2
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: sweet16-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'sweet16' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.name = parts[1]  # Case sensitive
        self.material = parts[2].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file
        template_file = os.path.join(template_dir, "sweet16_template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the elements with id="Name" and id="Name2" and update their content
        for elem in root.iter():
            if 'id' in elem.attrib:
                if elem.attrib['id'] == 'Name' or elem.attrib['id'] == 'Name2':
                    # For SVG text elements, the text is usually in a child element or as text content
                    if len(elem) > 0:  # If it has child elements
                        for child in elem:
                            if child.text:
                                child.text = self.name + "'s"
                    else:  # If it has direct text content
                        elem.text = self.name + "'s"
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Baby product type class
class Baby(ProductType):
    """Class for handling Baby product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 2
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: baby-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'baby' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.name = parts[1]  # Case sensitive
        self.material = parts[2].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file
        template_file = os.path.join(template_dir, "baby_template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Congrats product type class
class Congrats(ProductType):
    """Class for handling Congrats product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.year = ""
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: congrats-<year>-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'congrats' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.year = parts[1].lower()  # Not case sensitive
        self.name = parts[2].upper()  # CAPITALIZE the entire name
        self.material = parts[3].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file based on year
        template_file = os.path.join(template_dir, f"congrats-{self.year}-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Feliz product type class
class Feliz(ProductType):
    """Class for handling Feliz product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.age = ""
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: feliz-<age>-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'feliz' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.age = parts[1].lower()  # Not case sensitive
        self.name = parts[2].upper()  # CAPITALIZE the entire name
        self.material = parts[3].lower()  # Not case sensitive
        
        # Validate age
        if self.age != "noage" and not self.age.isdigit():
            raise ValueError("Age must be either a number or 'noage'")
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Determine which template to use based on age
        if self.age == "noage":
            template_file = os.path.join(template_dir, "feliz-noage-template.svg")
        else:
            template_file = os.path.join(template_dir, "feliz-age-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Design product type class
class Design(ProductType):
    """Class for handling Design product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 2
        self.style = ""
        self.initial_1 = ""
        self.initial_2 = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: design<style>-<initial_1><initial_2>-<material>"""
        # First, extract the style number from the product type
        parts = self.filename.split('-')
        if not parts:
            raise ValueError("Invalid filename format")
        
        # Extract the product type and check if it starts with "design"
        product_type = parts[0].lower()
        if not product_type.startswith("design"):
            raise ValueError("Product type must start with 'design'")
        
        # Extract the style number
        self.style = product_type[6:]  # Remove "design" prefix
        if not self.style.isdigit() or int(self.style) < 1 or int(self.style) > 6:
            raise ValueError("Style must be a number between 1 and 6")
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'design<style>' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the initials and material
        initials = parts[1]
        if len(initials) != 2:
            raise ValueError("Initials must be exactly 2 characters")
        
        self.initial_1 = initials[0].upper()  # CAPITALIZE
        self.initial_2 = initials[1].upper()  # CAPITALIZE
        self.material = parts[2].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file based on style
        template_file = os.path.join(template_dir, f"design{self.style}-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the elements with id="initial_1" and id="initial_2" and update their content
        initial_1_element = None
        initial_2_element = None
        
        for elem in root.iter():
            if 'id' in elem.attrib:
                if elem.attrib['id'] == 'initial_1':
                    initial_1_element = elem
                elif elem.attrib['id'] == 'initial_2':
                    initial_2_element = elem
        
        # Update initial_1
        if initial_1_element is not None:
            if len(initial_1_element) > 0:  # If it has child elements
                for child in initial_1_element:
                    if child.text:
                        child.text = self.initial_1
            else:  # If it has direct text content
                initial_1_element.text = self.initial_1
        
        # Update initial_2
        if initial_2_element is not None:
            if len(initial_2_element) > 0:  # If it has child elements
                for child in initial_2_element:
                    if child.text:
                        child.text = self.initial_2
            else:  # If it has direct text content
                initial_2_element.text = self.initial_2
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Moon product type class
class Moon(ProductType):
    """Class for handling Moon product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 2
        self.name = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: moon-<name>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'moon' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.name = parts[1]  # Case sensitive - store exactly as written
        self.material = parts[2].lower()  # Not case sensitive
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file
        template_file = os.path.join(template_dir, "moon-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Name" and update its content
        name_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Name':
                name_element = elem
                break
        
        if name_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(name_element) > 0:  # If it has child elements
                for child in name_element:
                    if child.text:
                        child.text = self.name
            else:  # If it has direct text content
                name_element.text = self.name
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the NumberCharm product type class
class NumberCharm(ProductType):
    """Class for handling NumberCharm product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 3
        self.number = ""
        self.size = ""
        self.material = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: numberCHARM-<number>-<size>-<material>"""
        parts = self.filename.split('-')
        
        # Check if we have the right number of parts
        if len(parts) != self.expected_input_qty + 1:  # +1 for the 'numberCHARM' prefix
            raise ValueError(f"Expected {self.expected_input_qty + 1} parts in filename, got {len(parts)}")
        
        # Extract the values
        self.number = parts[1].lower()  # Not case sensitive
        self.size = parts[2].lower()  # Not case sensitive
        self.material = parts[3].lower()  # Not case sensitive
        
        # Validate size
        valid_sizes = ["small", "standard", "large"]
        if self.size not in valid_sizes:
            raise ValueError(f"Size must be one of {valid_sizes}, got '{self.size}'")
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file based on size
        template_file = os.path.join(template_dir, f"numberCHARM-{self.size}-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Number" and update its content
        number_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Number':
                number_element = elem
                break
        
        if number_element is not None:
            # For SVG text elements, the text is usually in a child element or as text content
            if len(number_element) > 0:  # If it has child elements
                for child in number_element:
                    if child.text:
                        child.text = self.number
            else:  # If it has direct text content
                number_element.text = self.number
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

# Define the Plant product type class
class Plant(ProductType):
    """Class for handling Plant product type"""
    def __init__(self, filename):
        # Define expected properties
        self.expected_input_qty = 2
        self.font = ""
        self.text = ""
        super().__init__(filename)
    
    def parse_filename(self):
        """Parse the filename format: plant-<font>-<text>"""
        # Split only on the first two dashes to preserve remaining dashes in text
        parts = self.filename.split('-', 2)  # Split into max 3 parts
        
        # Check if we have enough parts (need at least product type, font, and some text)
        if len(parts) != 3:  # We need exactly 3 parts: plant, font, and text
            raise ValueError("Format must be: plant-<font>-<text>")
        
        # Extract the values
        self.font = parts[1].lower()  # Not case sensitive
        self.text = parts[2]  # Case sensitive - store exactly as written
        
        # Validate font
        valid_fonts = ["tall", "cursive", "typewriter"]
        if self.font not in valid_fonts:
            raise ValueError(f"Font must be one of {valid_fonts}, got '{self.font}'")
    
    def create_file(self, project_dir):
        """Create a new file from template"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use template directory relative to the script location
        template_dir = os.path.join(script_dir, "_TEMPLATES")
        
        # Get the template file based on font
        template_file = os.path.join(template_dir, f"plant-{self.font}-template.svg")
        
        # Check if the template file exists
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"Template file {template_file} not found")
        
        # Create output filename
        encoded_filename = encode_case(self.filename)
        output_file = os.path.join(project_dir, f"{encoded_filename}.svg")
        
        if os.path.exists(output_file):
            base, ext = os.path.splitext(output_file)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            output_file = f"{base}_{i}{ext}"
        
        # Load template and modify text
        tree = ET.parse(template_file)
        root = tree.getroot()
        
        # Find the element with id="Plant-Text" and update its content
        text_element = None
        for elem in root.iter():
            if 'id' in elem.attrib and elem.attrib['id'] == 'Plant-Text':
                text_element = elem
                break
        
        if text_element is not None:
            # Replace dashes with spaces in the display text
            display_text = self.text.replace('-', ' ')
            
            # For SVG text elements, the text is usually in a child element or as text content
            if len(text_element) > 0:  # If it has child elements
                for child in text_element:
                    if child.text:
                        child.text = display_text
            else:  # If it has direct text content
                text_element.text = display_text
        
        # Save modified SVG
        tree.write(output_file)
        return output_file

def encode_case(filename):
    """
    Encode uppercase letters in a filename with ^ prefix.
    Example: 'plant-cursive-Tomato' -> 'plant-cursive-^tomato'
    """
    result = []
    for char in filename:
        if char.isupper():
            result.append('^' + char.lower())
        else:
            result.append(char)
    return ''.join(result)

def decode_case(filename):
    """
    Decode a filename by removing ^ prefixes and converting to uppercase.
    Example: 'plant-cursive-^tomato' -> 'plant-cursive-Tomato'
    """
    result = []
    i = 0
    while i < len(filename):
        if i + 1 < len(filename) and filename[i] == '^':
            result.append(filename[i + 1].upper())
            i += 2
        else:
            result.append(filename[i])
            i += 1
    return ''.join(result)

def get_original_case(filename):
    """
    Get the original case of a filename by decoding the ^ prefixes.
    Example: 'plant-cursive-^tomato' -> 'plant-cursive-Tomato'
    """
    return decode_case(filename)

def check_existing_file(project_dir, fn_trunc, debug=False, also_check_project_dir=True):
    """
    Check if a file with the truncated name already exists in the 'done' directory
    and was modified in 2024 or later. If not found, optionally check project_dir.
    Returns:
    - (existing_file, is_recent, bbwood_file, found_in_project_dir) tuple if file exists
    - (None, None, None, False) if no file exists
    """
    done_dir = os.path.join(project_dir, "micah_done")
    encoded_fn_trunc = encode_case(fn_trunc)
    found_in_project_dir = False
    if not os.path.exists(done_dir):
        if debug:
            print(f"Debug: 'done' directory not found at {done_dir}")
        # skip to project_dir check
        matching_files = []
    else:
        matching_files = []
        parts = encoded_fn_trunc.split('-')
        product_type = parts[0].lower() if parts else ""
        if product_type == "plant":
            expected_file = f"{encoded_fn_trunc}.svg"
            for file in os.listdir(done_dir):
                if file == expected_file:
                    matching_files.append(file)
                    break
        else:
            pattern = f"^{re.escape(encoded_fn_trunc)}.*\\.svg$"
            for file in os.listdir(done_dir):
                if re.match(pattern, file):
                    matching_files.append(file)
    if matching_files:
        matching_files.sort(key=lambda x: os.path.getmtime(os.path.join(done_dir, x)), reverse=True)
        existing_file = os.path.join(done_dir, matching_files[0])
        mod_time = datetime.fromtimestamp(os.path.getmtime(existing_file))
        is_recent = mod_time.year >= 2024
        bbwood_file = None
        return existing_file, is_recent, bbwood_file, False
    # If not found in done_dir, check project_dir
    if also_check_project_dir:
        encoded_file = f"{encoded_fn_trunc}.svg"
        project_file_path = os.path.join(project_dir, encoded_file)
        if os.path.exists(project_file_path):
            found_in_project_dir = True
            mod_time = datetime.fromtimestamp(os.path.getmtime(project_file_path))
            is_recent = mod_time.year >= 2024
            return project_file_path, is_recent, None, True
    return None, None, None, False

def open_file_with_default_app(file_path):
    """Open a file with the default application"""
    if sys.platform == 'win32':
        os.startfile(file_path)
    elif sys.platform == 'darwin':  # macOS
        subprocess.call(['open', file_path])
    else:  # Linux and other Unix-like systems
        subprocess.call(['xdg-open', file_path])

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='SLS Shortcut Tool')
    parser.add_argument('project_dir', nargs='?', help='Project directory path')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--options', action='store_true', help='List all supported product types')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check if options flag is set
    if args.options:
        print("Supported product types:")
        print("  sm        - Format: sm-<name>-<size>-<material>")
        print("              Sizes: small, standard, large")
        print()
        print("  circle    - Format: circle-<age>-<name>-<material>")
        print("              Falls back to 'OTHER' template if age-specific template not found")
        print("              Name is automatically capitalized")
        print()
        print("  square    - Format: square-<age>-<name>-<material>")
        print("              Falls back to 'OTHER' template if age-specific template not found")
        print("              Name is automatically capitalized")
        print()
        print("  school    - Format: school-<font>-<name>-<material>")
        print("              Fonts: 1, 2, 3, 4")
        print("              Creates both regular and bbwood files")
        print()
        print("  cross     - Format: cross-<name>-<size>-<material>")
        print("              Sizes: small, standard")
        print()
        print("  gb        - Format: gb-<name>-<material>")
        print("              Uses the god_bless_template.svg template")
        print()
        print("  sweet16   - Format: sweet16-<name>-<material>")
        print("              Uses the sweet16_template.svg template")
        print()
        print("  baby      - Format: baby-<name>-<material>")
        print("              Uses the baby_template.svg template")
        print()
        print("  congrats  - Format: congrats-<year>-<name>-<material>")
        print("              Uses the congrats-<year>-template.svg template")
        print("              Name is automatically capitalized")
        print()
        print("  feliz     - Format: feliz-<age>-<name>-<material>")
        print("              Uses feliz-age-template.svg or feliz-noage-template.svg")
        print("              Age must be a number or 'noage'")
        print("              Name is automatically capitalized")
        print()
        print("  design1-6 - Format: design<style>-<initial_1><initial_2>-<material>")
        print("              Style must be a number between 1 and 6")
        print("              Initials must be exactly 2 characters")
        print("              Initials are automatically capitalized")
        print()
        print("  moon      - Format: moon-<name>-<material>")
        print("              Uses the moon-template.svg template")
        print("              Name is case sensitive")
        print()
        print("  numbercharm - Format: numberCHARM-<number>-<size>-<material>")
        print("              Uses numberCHARM-<size>-template.svg")
        print("              Size must be small, standard, or large")
        print("              Number and material are not case sensitive")
        print()
        print("  plant     - Format: plant-<font>-<text>")
        print("              Fonts: tall, cursive, typewriter")
        print("              Text is case sensitive")
        print("              Dashes in text are displayed as spaces in the final SVG")
        print()
        print("Example usage:")
        print("  > sm-John-standard-mdf")
        print("  > circle-80-MARY-oak")
        print("  > school-2-Emily-blue")
        print("  > cross-Michael-small-walnut")
        print("  > gb-Brady-mdf")
        print("  > sweet16-John-oak")
        print("  > baby-John-oak")
        return
    
    # Check if project directory was provided
    if not args.project_dir:
        parser.print_help()
        print("\nError: Project directory is required unless using --options")
        sys.exit(1)
    
    # Get project directory from command line argument
    project_dir = args.project_dir
    debug_mode = args.debug
    
    if debug_mode:
        print(f"Debug mode enabled")
    
    # Check if directory exists
    if not os.path.isdir(project_dir):
        print(f"Error: Directory '{project_dir}' does not exist.")
        sys.exit(1)
    
    # Main processing loop
    while True:
        try:
            # Get user input
            user_input = input("> ")

            # Exit condition (empty input)
            if not user_input:
                continue

            readline.add_history(user_input)

            # Store as FILENAME
            filename = user_input
            
            # Get product type (text before first "-")
            product_type = filename.split('-')[0].lower()
            
            # For plant type, we want to check the full filename
            if product_type == "plant":
                existing_file, is_recent, bbwood_file, found_in_project_dir = check_existing_file(project_dir, filename, debug_mode)
            else:
                last_hyphen_pos = filename.rfind('-')
                if last_hyphen_pos == -1:
                    print("Error: Input must contain at least one hyphen.")
                    continue
                fn_trunc = filename[:last_hyphen_pos + 1]
                existing_file, is_recent, bbwood_file, found_in_project_dir = check_existing_file(project_dir, fn_trunc, debug_mode)
            
            if existing_file:
                if is_recent:
                    # File exists and is recent, copy it
                    encoded_filename = encode_case(filename)
                    base_name = os.path.join(project_dir, f"{encoded_filename}")
                    ext = ".svg"
                    new_file = base_name + ext
                    i = 1
                    while os.path.exists(new_file):
                        new_file = f"{base_name}_{i}{ext}"
                        i += 1
                    shutil.copy(existing_file, new_file)
                    if found_in_project_dir:
                        print(f"Copied file from project directory: {new_file}")
                    else:
                        print(f"Copied recent file from 'done' directory: {new_file}")
                    
                    # For school product type, also copy the bbwood file if it exists
                    bbwood_new_file = None
                    if product_type == "school" and bbwood_file:
                        bbwood_new_file = os.path.join(project_dir, f"{encode_case(fn_trunc)}bbwood.svg")
                        shutil.copy2(bbwood_file, bbwood_new_file)
                        print(f"Copied bbwood file from 'done' directory: {bbwood_new_file}")
                    
                    # Do NOT open the file after copying an existing one
                    # if product_type == "school" and bbwood_new_file:
                    #     open_file_with_default_app(bbwood_new_file)
                    
                    continue
                else:
                    # File exists but is old, ask user
                    use_old = input(f"Found an older file (before 2024). Use it? (y/n): ").lower()
                    if use_old == 'y':
                        encoded_filename = encode_case(filename)
                        base_name = os.path.join(project_dir, f"{encoded_filename}")
                        ext = ".svg"
                        new_file = base_name + ext
                        i = 1
                        while os.path.exists(new_file):
                            new_file = f"{base_name}_{i}{ext}"
                            i += 1
                        shutil.copy2(existing_file, new_file)
                        print(f"Copied older file from 'done' directory: {new_file}")
                        
                        # For school product type, also copy the bbwood file if it exists
                        bbwood_new_file = None
                        if product_type == "school" and bbwood_file:
                            bbwood_new_file = os.path.join(project_dir, f"{encode_case(fn_trunc)}bbwood.svg")
                            shutil.copy2(bbwood_file, bbwood_new_file)
                            print(f"Copied bbwood file from 'done' directory: {bbwood_new_file}")
                        
                        # Do NOT open the file after copying an existing one
                        # if product_type == "school" and bbwood_new_file:
                        #     open_file_with_default_app(bbwood_new_file)
                        
                        continue
            
            # Continue with parsing if we didn't copy an existing file
            
            # Handle based on product type
            if product_type == "sm":
                handler = SM(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "circle":
                handler = Circle(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "square":
                handler = Square(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "school":
                handler = School(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "cross":
                handler = Cross(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "gb":
                handler = GB(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "sweet16":
                handler = Sweet16(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "baby":
                handler = Baby(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "congrats":
                handler = Congrats(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "feliz":
                handler = Feliz(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type.startswith("design"):
                handler = Design(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "moon":
                handler = Moon(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "numbercharm":
                handler = NumberCharm(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                # open_file_with_default_app(output_file)
            elif product_type == "plant":
                handler = Plant(filename)
                output_file = handler.create_file(project_dir)
                print(f"Created file: {output_file}")
                open_file_with_default_app(output_file)
            else:
                print(f"Unknown product type: {product_type}")
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            continue

if __name__ == "__main__":
    main()  