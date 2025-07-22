# Still in mesh/proto directory
for file in averaging_pb2.py calculator_protocol_pb2.py dht_pb2.py inference_protocol_pb2.py; do
    echo "Fixing $file..."
    sed -i 's/^import \([a-zA-Z_]*_pb2\) as \(.*\)/from . import \1 as \2/' "$file"
    echo "  ✓ Fixed $file"
done