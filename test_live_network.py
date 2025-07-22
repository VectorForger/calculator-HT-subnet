import asyncio
from mesh import DHT
from mesh.subnet.protocols.calculator_protocol import SimpleCalculatorProtocol
from mesh.subnet.utils.dht import get_node_infos

async def test_calculator_network():
    print("🧮 Testing calculator subnet...")
    
    # Connect to the network
    dht = DHT(
        initial_peers=["/ip4/127.0.0.1/tcp/31330/p2p/QmShJYgxNoKn7xqdRQj5PBcNfPSsbWkgFBPA4mK5PH73JB"],
        start=True
    )
    
    # Wait for connection
    await asyncio.sleep(5)
    print("📡 Connected to DHT network")
    
    # Find calculator nodes using the proper DHT API
    try:
        node_infos = get_node_infos(dht, uid="validator", latest=True)
        print(f"📡 Found {len(node_infos)} calculator nodes")
        
        if len(node_infos) > 0:
            # Get the first peer
            peer_id = node_infos[0].peer_id
            print(f"🎯 Using peer: {peer_id}")
            
            # Create client
            client = SimpleCalculatorProtocol(dht=dht, subnet_id=1, client=True, start=True)
            
            # Test calculations
            test_problems = ["4 * 3", "15 + 27", "100 / 4", "10 / 0"]
            
            for problem in test_problems:
                print(f"\n🔢 Testing: {problem}")
                try:
                    response = await client.call_peer_calculate(peer_id, problem)
                    if response.success:
                        print(f"✅ Result: {response.result}")
                    else:
                        print(f"❌ Error: {response.error}")
                except Exception as e:
                    print(f"❌ Exception: {e}")
        else:
            print("❌ No calculator nodes found in the network")
            
    except Exception as e:
        print(f"❌ Error finding peers: {e}")
    
    dht.shutdown()

if __name__ == "__main__":
    asyncio.run(test_calculator_network())