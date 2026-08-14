////////////////////////////////////////////////////////////////////////////////
// Initialization
////////////////////////////////////////////////////////////////////////////////
const myPrice = document.getElementById('myPrice');
const myQuantity = document.getElementById('myQuantity');
const myProposal = document.getElementById('myProposal');
const otherProposal = document.getElementById('otherProposal');

const btnChat = document.getElementById("btn-chat");
const btnOffer = document.getElementById("btn-offer");
const btnAccept = document.getElementById('btnAccept');
// TEST offer: enabled/disabled together with CONFIRM (both act on the
// counterpart's standing proposal; handler testOffer() lives in
// analysis.js next to the DSS it feeds).
const btnTest = document.getElementById('btnTest');

document.addEventListener('DOMContentLoaded', () => {
  if (js_vars.bot_opponent === true) {
    // Disable send buttons for bot opponent
    btnChat.disabled = true;
    myPrice.disabled = true;
    myQuantity.disabled = true;

    // Start the negotiations, needed here for event loop
    setTimeout(() => {
      liveSend({'type': 'initial'});
    }, 1000);
  }
  receiveMessage(js_vars.messages);
  receiveoffers(js_vars.offers);

  // Always disable offer button on (re)loading of page
  btnOffer.disabled = true;
  if (!otherProposal.innerHTML.includes('none')) {
    btnAccept.disabled = false;
    btnTest.disabled = false;
  }

  // Set the timer color to red if 30 seconds left
  $('.otree-timer__time-left').on('update.countdown', function (event) {
    if (event.offset.totalSeconds <= 30) {
      document.getElementsByClassName('time-left')[0].style.color = "#FF0000";
    }
  });

  setInterval(() => {
    liveSend({'type': 'ping'});
  }, 1000);
});

function liveRecv(data) {
  if ('finished' in data) {
    document.getElementById('form').submit();
  }
  if ('timer_reset' in data) {
    resetTimer(data.timer_reset);
  }
  if ('chat' in data) {
    receiveMessage(data.chat);
  }
  if ('offers' in data) {
    receiveoffers(data.offers);
  }
  if ('unblock' in data) {
    console.log("UNBLOCK received!");
    blockUnblock(false);
  }
}

////////////////////////////////////////////////////////////////////////////////
// Timer reset (server pushes 'timer_reset' when an offer arrives with
// less than 30 seconds left; the server-side deadline was already moved)
////////////////////////////////////////////////////////////////////////////////
function resetTimer(seconds) {
  // Re-initializing the jQuery countdown with a new target keeps the
  // update./finish.countdown handlers (they live on the DOM element), so
  // the page still auto-submits when the NEW deadline expires.
  $('.otree-timer__time-left').countdown(
      new Date().valueOf() + seconds * 1000);
}

////////////////////////////////////////////////////////////////////////////////
// Blocking functionality
////////////////////////////////////////////////////////////////////////////////
let blockedChat = js_vars.bot_opponent;
let blockedOffer = js_vars.bot_opponent;
let blockCount = 0;

function blockUnblock(block) {
  if (js_vars.bot_opponent !== true) {
    return;
  }

  blockedChat = btnChat.disabled = block;

  blockedOffer = block;
  if (blockedOffer === true) {
    btnOffer.disabled = true;
    myPrice.disabled = true;
    myQuantity.disabled = true;
  } else {
    myPrice.disabled = false;
    myQuantity.disabled = false;
    // Price has been entered, Quantity has been entered
    if (myPrice.value !== "" && myQuantity.value !== "") {
      btnOffer.disabled = false;
    }
  }
  myPrice.placeholder = "Price here..."
}

function unblockAfterMessage() {
  if (js_vars.bot_opponent !== true) {
    return;
  }
  let nicks = chatOutput.getElementsByClassName('otree-chat__nickname');

  blockCount = 0;
  Array.from(nicks).forEach((n) => {
    blockCount += n.innerHTML.includes("(Me)");
  });

  let lastNick = nicks[nicks.length - 1].innerHTML;
  if (!lastNick.includes("(Me)")) {
    blockUnblock(false);
  }
}

function unblockBtnOffer() {
  btnOffer.disabled = !(myPrice.value.trim() !== "" && myQuantity.value.trim() !== "" && blockedOffer === false);
}

////////////////////////////////////////////////////////////////////////////////
// Bargain functionality
////////////////////////////////////////////////////////////////////////////////
myPrice.addEventListener("keydown", function (event) {
  let key = event.key;
  // Always allow Delete and Backspace
  if (["Delete", "Backspace"].includes(key)) {
    unblockBtnOffer();
    return;
  }

  // Only allow numbers and dot
  if (isNaN(parseFloat(key)) && key !== '.') {
    event.preventDefault();
    return;
  }

  // Prevent multiple decimal points
  if (key === "." && myPrice.value.includes(".")) {
    event.preventDefault();
    return;
  }

  // Prevent more than 2 decimal places
  if (myPrice.value.includes(".") && myPrice.value.split(".")[1].length >= 2) {
    event.preventDefault();
    return;
  }
  unblockBtnOffer();
});

myQuantity.addEventListener("keydown", function (event) {
  let key = event.key;
  // Always allow Delete and Backspace
  if (["Delete", "Backspace"].includes(key)) {
    unblockBtnOffer();
    return;
  }

  // Allow only numbers
  if (isNaN(parseInt(key))) {
    event.preventDefault();
    return;
  }
  unblockBtnOffer();
});

myPrice.addEventListener("input", function () {
  // Clamp the wholesale price to [price_min, price_max] as you type,
  // mirroring the quantity clamp below: "0" becomes 1, "300" becomes 5.
  // Only rewrite the field when the clamp actually changes the numeric
  // value, so intermediate states like "3." keep their decimal point.
  if (myPrice.value !== "") {
    let value = parseFloat(myPrice.value);
    if (!isNaN(value)) {
      let clamped = Math.min(Math.max(value, js_vars.price_min),
          js_vars.price_max);
      if (clamped !== value) {
        myPrice.value = clamped;
      }
    }
  }
  unblockBtnOffer();
});

myQuantity.addEventListener("input", function () {
  // Ensure the input is an integer
  myQuantity.value = myQuantity.value.replace(/[^0-9]/g, ""); // Remove non-numeric characters

  // Enforce minimum and maximum values
  if (myQuantity.value !== "") {
    let value = parseInt(myQuantity.value);
    value = Math.max(value, 1);
    myQuantity.value = Math.min(value, js_vars.demand_max);
  }
  unblockBtnOffer();
});

function sendOffer() {
  let price = parseFloat(myPrice.value);
  let quantity = parseInt(myQuantity.value);
  if (!isNaN(price) && !isNaN(quantity)) {
    liveSend({'type': 'propose', 'price': price, 'quantity': quantity})
  }
  myPrice.value = "";
  myQuantity.value = "";
  btnOffer.disabled = true;
  blockUnblock(true);
}

function sendAccept() {
  btnChat.disabled = true;
  btnOffer.disabled = true;
  btnAccept.disabled = true;
  btnTest.disabled = true;

  let proposal = otherProposal.innerHTML;
  let price = parseFloat(proposal.split('<br>')[0].replace('€', ''));
  if (isNaN(price)) {
    return;
  }
  let quantity = parseInt(proposal.split('<br>')[1]);
  liveSend({'type': 'accept', 'price': price, 'quantity': quantity})
}

function receiveoffers(offers) {
  offers.forEach((offer) => {
    if (offer['price'] !== null && offer['quantity'] !== null) {
      let innerHTML = `€ ${offer['price']}<br>${offer['quantity']}`;
      if (offer['idx'] === js_vars.id_in_group) {
        myProposal.innerHTML = innerHTML;
      } else {
        otherProposal.innerHTML = innerHTML;
        btnAccept.disabled = false;
        btnTest.disabled = false;
      }
    }
  });
}

////////////////////////////////////////////////////////////////////////////////
// Chat functionality
////////////////////////////////////////////////////////////////////////////////
const chatOutput = document.getElementById("chat-output");
const chatInput = document.getElementById("chat-input");

chatInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && blockedChat === false) {
    sendMessage();
  }
});

function sendMessage() {
  let body = chatInput.value;
  if (body === "") {
    return;
  }

  liveSend({'type': 'chat', 'body': body});

  chatInput.value = "";
  blockUnblock(true);
}

function receiveMessage(messages) {
  let messagesHTML = '';
  messages.forEach((message) => {
    let nick = escapeHtml(message['nick']);
    let body = escapeHtml(message['body']).replaceAll('\n', '<br>');
    messagesHTML += "<div class='otree-chat__msg'>" +
        "<span class='otree-chat__nickname'>" + nick + "</span>" +
        "<span class='otree-chat__body'>" + body + "</span>" +
        "</div>";
  });
  messagesHTML += "<div class='otree-chat__msg'>&nbsp;</div>";
  chatOutput.innerHTML = messagesHTML;
  chatOutput.scrollTo({
    top: chatOutput.scrollHeight,
    left: 0,
    behavior: "smooth",
  });
  if (messages.length > 0) {
    unblockAfterMessage();
  }
}

function escapeHtml(string) {
  let entityMap = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
    '/': '&#x2F;',
    '`': '&#x60;',
    '=': '&#x3D;'
  };

  return String(string).replace(/[&<>"'`=\/]/g, function (s) {
    return entityMap[s];
  });
}
