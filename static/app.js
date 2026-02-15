async function search_endpoint() {

    const input = document.getElementById("searchInput").value;
    
    // EncodeURIComponent allows for spaces, special chars, etc
    const response = await fetch(`/search?str=${encodeURIComponent(input)}`);
    const data = await response.json();
    console.log(data)

    document.getElementById("output").innerText = JSON.stringify(data);

     output.innerHTML = "";

    if (data.length === 0) {
        output.innerHTML = "<p>No results found.</p>";
        return;
    }

    data.forEach(item => {
        const card = document.createElement("div");
        card.className = "card";

        card.innerHTML = `
            <h3>${item.title}</h3>
            <p><strong>Agency:</strong> ${item.agency_id}</p>
            <p><strong>Docket:</strong> ${item.docket_id}</p>
            <p><strong>Type:</strong> ${item.document_type}</p>
            <p><strong>CFR:</strong> ${item.cfrPart}</p>
        `;

        output.appendChild(card);
    });
}
