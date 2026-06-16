import requests, json

# Test the components API
try:
    r = requests.get("http://127.0.0.1:8000/components/10", timeout=5)
    data = r.json()
    cells = [c for c in data if c['component_type'] == 'CELL']
    print(f"Total components for doc 10: {len(data)}")
    print(f"CELLs: {len(cells)}")
    if cells:
        cell = cells[0]
        print(f"\nFirst CELL:")
        print(f"  id: {cell['id']}")
        print(f"  component_type: {cell['component_type']}")
        print(f"  bbox: {cell['bbox']}")
        print(f"  manifest_path: {cell.get('manifest_path')}")
        print(f"  predictions: {cell.get('predictions', [])}")
except requests.ConnectionError:
    print("Server not running on port 8000")
except Exception as e:
    print(f"Error: {e}")

# Test cell-image endpoint
try:
    r = requests.get("http://127.0.0.1:8000/cell-image/38", timeout=5)
    print(f"\nCell image endpoint: status={r.status_code}, content-type={r.headers.get('content-type')}, size={len(r.content)} bytes")
except requests.ConnectionError:
    print("Server not running on port 8000 (cell image test)")
except Exception as e:
    print(f"Cell image error: {e}")
