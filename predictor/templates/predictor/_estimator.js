(() => {
  // Elevação esquemática, desenhada localmente para funcionar também sem serviços de imagem.
  const canvas = document.getElementById("house");
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.scale(2, 2);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    const edge = "#ccd6a6", soft = "#86a790";
    function line(points, color = edge, width = 1, fill = null) {
      ctx.beginPath();
      points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      if (fill) { ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); }
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();
    }
    line([[30,102],[188,126],[328,85]],soft,.6);
    line([[45,107],[173,127]],soft,.5);
    // Ala baixa, caixilhos e cobertura plana.
    line([[165,66],[251,78],[251,112],[165,99]],edge,1,"#264f40");
    line([[251,78],[290,60],[290,94],[251,112]],edge,1,"#1c4339");
    line([[164,66],[202,49],[290,60],[251,78]],edge,1,"#315346");
    line([[163,66],[251,79],[292,60]],edge,1.4);
    line([[186,78],[242,86],[242,106],[186,98]],edge,.8,"#173c34");
    for(let i=0;i<5;i++) line([[192+i*10,79+i*1.43],[192+i*10,99+i*1.43]],soft,.7);
    for(let i=0;i<8;i++) line([[257+i*4,80-i*1.85],[257+i*4,105-i*1.85]],soft,.65);
    // Volume principal com telhado de duas águas e varanda.
    line([[65,66],[110,31],[163,80],[163,113],[65,98]],edge,1.2,"#315646");
    line([[163,80],[211,58],[211,91],[163,113]],edge,1.2,"#1d4539");
    line([[58,67],[109,25],[162,75],[158,79],[110,33],[63,73]],edge,1,"#446653");
    line([[109,25],[157,7],[215,54],[162,75]],edge,1.2,"#355949");
    for(let i=1;i<=7;i++) line([[110+i*6,25-i*2.25],[162+i*6.3,74-i*2.4]],soft,.65);
    line([[162,75],[215,54],[215,59],[162,81]],edge,1,"#21483b");
    line([[68,74],[160,88]],soft,.8);
    line([[76,75],[102,79],[102,98],[76,94]],edge,.8,"#173e34");
    line([[89,77],[89,96]],soft,.8);
    line([[113,81],[131,84],[131,106],[113,103]],edge,.8,"#173e34");
    for(let i=0;i<4;i++) line([[136+i*5,84+i*.75],[136+i*5,107+i*.75]],soft,.65);
    line([[63,98],[163,114],[213,91]],edge,1.2);
    line([[109,103],[132,106],[126,109],[103,106]],soft,.8,"#315646");
    line([[103,106],[126,109],[121,112],[98,109]],soft,.7);
    // Linhas de cota da fachada.
    line([[60,113],[159,128]],soft,.55);
    line([[60,110],[60,116]],soft,.65); line([[159,125],[159,131]],soft,.65);
  }

  const byId = id => document.getElementById(id);
  const form = byId("form");
  const money = new Intl.NumberFormat("pt-BR", {style:"currency", currency:"BRL", maximumFractionDigits:0});
  const prompt = byId("hint").textContent;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (byId("btn").disabled) return;
    byId("btn").disabled = true;
    byId("button-label").textContent = "Calculando…";
    byId("resultado").hidden = true;
    byId("empty").hidden = false;
    byId("hint").textContent = "Consultando o endereço e os anúncios semelhantes…";
    byId("erro").hidden = true;
    const data = {endereco: byId("endereco").value.trim(), condominio: byId("condominio").checked,
                  n_amenities: form.querySelectorAll(".am:checked").length};
    for (const key of ["area","quartos","banheiros","suites","vagas"]) data[key] = Number(byId(key).value);
    try {
      const response = await fetch(form.action, {method: "POST", headers: {
        "Content-Type":"application/json", "X-CSRFToken": form.elements.csrfmiddlewaretoken.value
      }, body: JSON.stringify(data)});
      if (!response.headers.get("content-type")?.includes("application/json"))
        throw new Error("Não foi possível consultar o servidor. Atualize a página e tente novamente.");
      const result = await response.json();
      if (!response.ok || result.erro) throw new Error(result.erro || "Não foi possível calcular o preço.");
      byId("preco").textContent = money.format(result.preco);
      byId("faixa").textContent = [result.intervalo_min,result.intervalo_max].map(n => money.format(n)).join(" a ");
      const bairros = (result.zona_bairros || []).slice(0,2).join(", ");
      byId("viz").textContent = "Região " + result.zona + (bairros ? " · " + bairros : "") +
        " · " + result.vizinhos_2km + " imóveis em até 2 km.";
      byId("aviso").textContent = result.aviso || "";
      byId("aviso").hidden = !result.aviso;
      byId("empty").hidden = true;
      byId("resultado").hidden = false;
      if (window.matchMedia("(max-width: 820px)").matches) byId("estimate-card").focus();
    } catch (error) {
      byId("hint").textContent = prompt;
      byId("erro").textContent = error instanceof TypeError ? "Falha de conexão. Tente novamente." : error.message;
      byId("erro").hidden = false;
    } finally {
      byId("btn").disabled = false;
      byId("button-label").textContent = "Estimar preço";
    }
  });
})();
