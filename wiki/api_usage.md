# API Usage

The Piply OPDF backend exposes several REST API endpoints for document processing and validation.

## Document Management

* **`POST /upload`**
  Uploads a document (PDF or Image) to the server.
  * **Payload**: `multipart/form-data` with `file` field.
  * **Returns**: Document metadata including `id` and `status`.

* **`GET /documents`**
  Retrieves a list of all uploaded documents.
  * **Returns**: Array of document objects.

* **`GET /documents/{document_id}`**
  Retrieves metadata for a specific document.

* **`DELETE /documents/{document_id}`**
  Deletes a document from the database and removes all associated files from the storage.

## Processing

* **`POST /process/{document_id}`**
  Triggers the Piply extraction pipeline and OCR in the background.
  * **Returns**: Background job status.

## Components & OCR

* **`GET /components/{document_id}`**
  Retrieves all extracted components (Tables, Rows, Cells, etc.) for a processed document, including bounding boxes and OCR predictions.

* **`GET /cell-image/{component_id}`**
  Serves the cropped PNG image for a specific CELL component.

* **`POST /ocr-cell/{component_id}`**
  Runs the 3-Layer OCR process on-demand for a specific CELL.
  * **Returns**: Predicted text and confidence score.

* **`POST /ocr-all/{document_id}`**
  Triggers a background job to run OCR on all extracted CELLs within a document.

## Feedback & Validation

* **`POST /feedback/{prediction_id}`**
  Submits human feedback or corrections for an OCR prediction.
  * **Payload**: `{"user_value": "Corrected Text", "is_accepted": true}`

* **`POST /feedback/bulk`**
  Bulk accepts multiple predictions at once.
  * **Payload**: `{"prediction_ids": [1, 2, 3], "is_accepted": true}`
