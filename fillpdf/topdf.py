import pdfrw
from pdfrw import PdfReader, PdfWriter, PageMerge, PdfName
from reportlab.pdfgen import canvas
from io import BytesIO


def fill_and_flatten_pdf(input_pdf_path, data_dict):
    # Lire le PDF modèle
    template_pdf = PdfReader(input_pdf_path)
    
    # Itérer sur chaque page
    for page_number, page in enumerate(template_pdf.pages, start=1):
        print(f"Processing page {page_number}")
        # Dimensions de la page
        media_box = page.MediaBox
        page_width = float(media_box[2]) - float(media_box[0])
        page_height = float(media_box[3]) - float(media_box[1])
        
        # Créer un PDF avec ReportLab pour cette page
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))
        annotations = page.Annots
        if annotations:
            for annotation in annotations:
                if annotation.Subtype == PdfName.Widget:
                    field_name = annotation.get(PdfName.T)
                    field_type = annotation.get(PdfName.FT)
                    if field_name is not None:
                        field_name_clean = field_name.strip('()')
                        if field_name_clean in data_dict:
                            print(field_name_clean)
                            field_value = data_dict[field_name_clean]
                            if field_type == PdfName.Btn and annotation.get(PdfName.Ff) == 49152:  # 49152 is the flag for checkboxes
                                # Gérer les cases à cocher
                                if str(field_value).lower() in ['yes', 'x', 'on', 'oui', 'true', '1']:
                                    value = PdfName.Yes
                                else:
                                    value = PdfName.Off
                                    print(value)
                                annotation.update(
                                    pdfrw.PdfDict(
                                        V=value,
                                        AS=value  # Update both the value and appearance state for checkboxes
                                    )
                                )
                            else:
                                # Gérer les champs de texte
                                rect = annotation.Rect
                                x1, y1, x2, y2 = [float(val) for val in rect]
                                field_height = y2 - y1
                                y = y1
                                can.setFont("Helvetica", 10)
                                can.drawString(x1 + 2, y + (field_height / 2) - 5, str(field_value))
        can.showPage()       
        can.showPage()
        can.save()

        # Déplacer au début du buffer BytesIO
        packet.seek(0)
        overlay_pdf = PdfReader(packet)
        if overlay_pdf.pages:
            overlay_page = overlay_pdf.pages[0]
            PageMerge(page).add(overlay_page).render()
        else:
            print(f"No content to overlay on page {page_number}.")
        
        # Supprimer les champs de formulaire de la page
        page.Annots = []

    # Retourner le PDF rempli et aplati sous forme de bytes
    output_pdf_bytes = BytesIO()
    PdfWriter().write(output_pdf_bytes, template_pdf)
    output_pdf_bytes.seek(0)  # Revenir au début du buffer
    return output_pdf_bytes.getvalue()  #

# Appeler la fonction pour remplir et aplatir le PDF
#fill_and_flatten_pdf(template_path, data, output_path)
