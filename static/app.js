async function search_endpoint() {

    const input = document.getElementById("searchInput").value;
    const filter = document.getElementById("filterSelect").value;
    
    // EncodeURIComponent allows for spaces, special chars, etc
    const response = await fetch(`/search/?str=${encodeURIComponent(input)}&filter=${encodeURIComponent(filter)}`);
    const data = await response.json();
    console.log(data)

    document.getElementById("output").innerText = JSON.stringify(data);
}
