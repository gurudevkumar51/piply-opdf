# UI Usage

This guide explains how to use the Piply OPDF web interface.

## 1. Document Upload
- On the top bar, click the **Upload New** button.
- Select a valid file (e.g., `.pdf`, `.png`, `.jpg`).
- The document will be uploaded and added to your selection list.

## 2. Processing
- Once a document is selected, click **Process Document**.
- This will trigger the background Piply extraction pipeline and 3-layer OCR process.
- Monitor the status badge (it will switch from `processing` to `completed`).

## 3. Document Viewer
- **View Modes**: Switch between `Original` (the raw PDF/Image) and `Enhanced (Extracted)` (which allows overlaying component bounding boxes).
- **Navigation**: Use the Prev/Next buttons to browse through pages.
- **Zoom**: Use Zoom In/Out/Fit Width controls to adjust visibility.

## 4. Component Explorer (Right Panel)
- Use the tabs (`Tables`, `Borderless`, `Rows`, `Columns`, `Cells`, `Headers`, `Footers`) to explore extracted components.
- Clicking on any component in the list will automatically scroll the document viewer to highlight its bounding box (requires `Enhanced` view mode).

## 5. OCR Review (Cells)
- When you click on a `CELL` component, the **OCR Review** panel populates.
- **Cell Image**: Displays the cropped image of that specific cell.
- **Predicted Text**: Displays the OCR result.
- **Confidence**: Displays the confidence score of the OCR.
- **Correction**: If the OCR is incorrect, type the correct value into the text area and click **Accept** to submit manual feedback.

## 6. Management
- Click **Manage** in the top navigation to view a list of all documents.
- From here, you can delete old or failed documents to clear database and storage space.
