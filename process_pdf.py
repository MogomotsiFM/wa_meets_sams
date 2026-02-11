import re

from pypdf import PdfReader, PdfWriter

def search_pdf(filepath):
    reader = PdfReader(filepath)
    for page in reader.pages:
        text = page.extract_text()

        match = re.search("Learner: (?P<surname>[-a-zA-Z ]*) , (?P<names>[-a-zA-Z ]*)", text)
        surname = match.group("surname")
        names = match.group("names")

        match = re.search(u"Admission No: (?P<admission_no>\d*)", text)
        admission_no = match.group("admission_no")
        print(f"Surname: {surname}, Names: {names}, Admission no: {admission_no}")

        print("\n\n")

    writer = PdfWriter(clone_from=reader)

    # Add a password to the new PDF
    writer.encrypt("12345", algorithm="AES-256")

    # Save the new PDF to a file
    writer.write("out-encrypt.pdf")



# Example: search for "invoice"
pages_with_term = search_pdf("C:\\Users\\GAME\\Documents\\Reports.pdf")
print(f"Found 'learner' on pages: {pages_with_term}")