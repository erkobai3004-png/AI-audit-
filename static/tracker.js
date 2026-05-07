let startTime = Date.now();

function sendData(data) {
    fetch("/track", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    });
}

window.onload = function () {
    sendData({
        site: document.body.dataset.site,
        event: "visit",
        referrer: document.referrer,
        time_spent: 0
    });
};

window.onbeforeunload = function () {
    sendData({
        site: document.body.dataset.site,
        event: "leave",
        referrer: document.referrer,
        time_spent: Math.round((Date.now() - startTime) / 1000)
    });
};

function clickButton(type) {
    sendData({
        site: document.body.dataset.site,
        event: "click",
        clicked: type,
        time_spent: Math.round((Date.now() - startTime) / 1000)
    });
}

function loginAttempt() {
    let login = document.getElementById("login").value;
    let pass = document.getElementById("password").value;

    sendData({
        site: document.body.dataset.site,
        event: "login_attempt",
        login_entered: login.length > 0 ? "yes" : "no",
        password_entered: pass.length > 0 ? "yes" : "no",
        time_spent: Math.round((Date.now() - startTime) / 1000)
    });
}
