backend-api/conversation/

window.open().window.document.body.innerText = Object.values(x.mapping)
    .map(e=>e?.message?.content?.parts?.[0])
    .filter(Boolean)
    .join("\n\n---------------------\n\n");
