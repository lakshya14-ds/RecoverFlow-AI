/* Customer portal: one-invoice bill view, disputes, evidence, payment refs. */
(function () {
    "use strict";
    var params = new URLSearchParams(window.location.search);
    var token = params.get("token") || "";
    var banner = document.getElementById("portal-banner");

    function showBanner(text, kind) {
        banner.hidden = false;
        banner.textContent = text;
        banner.className = "portal-banner" + (kind ? " " + kind : "");
    }

    function authHeaders(extra) {
        var headers = {"X-PORTAL-TOKEN": token};
        if (extra) {
            for (var key in extra) {
                if (Object.prototype.hasOwnProperty.call(extra, key)) {
                    headers[key] = extra[key];
                }
            }
        }
        return headers;
    }

    function explainStatus(res) {
        if (res.status === 410) {
            return "This link has expired. Please ask the business for a new one.";
        }
        if (res.status === 403) {
            return "This link is invalid or has been revoked. Please ask the business for a new one.";
        }
        if (res.status === 429) {
            return "Too many requests. Please wait a few minutes and try again.";
        }
        return "Something went wrong. Please try again later.";
    }

    function money(value, currency) {
        return (currency || "INR") + " " + value;
    }

    function friendlyStatus(status) {
        var labels = {open: "Open", disputed: "Disputed — under review",
            partially_paid: "Partly paid", paid: "Paid", adjusted: "Adjusted"};
        return labels[status] || status;
    }

    function load() {
        if (!token) {
            showBanner("This page needs a portal link from the business. " +
                "Open the link you received instead of this page directly.", "error");
            return;
        }
        fetch("/api/v1/portal/case", {headers: authHeaders()}).then(function (res) {
            if (!res.ok) {
                showBanner(explainStatus(res), "error");
                return null;
            }
            return res.json();
        }).then(function (body) {
            if (!body) {
                return;
            }
            document.getElementById("bill-number").textContent = body.invoice_number;
            document.getElementById("bill-status").textContent = friendlyStatus(body.status);
            document.getElementById("bill-total").textContent = money(body.total, body.currency);
            document.getElementById("bill-received").textContent = money(body.received, body.currency);
            document.getElementById("bill-outstanding").textContent = money(body.outstanding, body.currency);
            document.getElementById("bill-disputed").textContent = money(body.disputed, body.currency);
            document.getElementById("bill-due").textContent = body.due_date || "—";
            document.getElementById("bill-expiry").textContent =
                body.access_expires_at ? new Date(body.access_expires_at).toLocaleString() : "—";
            ["bill-card", "dispute-card", "evidence-card", "payref-card"].forEach(function (id) {
                document.getElementById(id).hidden = false;
            });
            var list = document.getElementById("submissions-list");
            list.innerHTML = "";
            (body.submissions || []).forEach(function (item) {
                var li = document.createElement("li");
                li.textContent = item.category + " — " + item.review +
                    (item.created_at ? " (" + new Date(item.created_at).toLocaleString() + ")" : "");
                list.appendChild(li);
            });
            if ((body.submissions || []).length) {
                document.getElementById("submissions-card").hidden = false;
            }
            loadEvidence();
        }).catch(function () {
            showBanner("Could not reach the server. Check your connection and try again.", "error");
        });
    }

    function loadEvidence() {
        fetch("/api/v1/portal/evidence", {headers: authHeaders()}).then(function (res) {
            return res.ok ? res.json() : [];
        }).then(function (items) {
            var list = document.getElementById("evidence-list");
            list.innerHTML = "";
            (items || []).forEach(function (item) {
                var li = document.createElement("li");
                var link = document.createElement("a");
                link.href = "/api/v1/portal/evidence/" + item.doc_id + "/file?token=" +
                    encodeURIComponent(token);
                link.textContent = item.filename;
                li.appendChild(link);
                li.appendChild(document.createTextNode(" — " + item.scan_status));
                list.appendChild(li);
            });
        });
    }

    document.getElementById("dispute-form").addEventListener("submit", function (event) {
        event.preventDefault();
        var form = event.target;
        var payload = {body: form.body.value.trim()};
        if (form.amount.value) {
            payload.amount = form.amount.value;
        }
        fetch("/api/v1/portal/disputes", {
            method: "POST",
            headers: authHeaders({"Content-Type": "application/json"}),
            body: JSON.stringify(payload)
        }).then(function (res) {
            if (!res.ok) {
                showBanner(explainStatus(res), "error");
                return null;
            }
            return res.json();
        }).then(function (body) {
            if (!body) {
                return;
            }
            form.reset();
            showBanner(body.is_injection
                ? "Your message was held for manual review."
                : "Dispute received. The business will review it.", "ok");
            load();
        });
    });

    document.getElementById("evidence-form").addEventListener("submit", function (event) {
        event.preventDefault();
        var form = event.target;
        var picked = form.file.files[0];
        if (!picked) {
            return;
        }
        fetch("/api/v1/portal/evidence", {
            method: "POST",
            headers: authHeaders({"X-Filename": picked.name, "X-Note": form.note.value || "",
                "Content-Type": picked.type || "application/octet-stream"}),
            body: picked
        }).then(function (res) {
            if (!res.ok) {
                if (res.status === 415 || res.status === 422 || res.status === 413) {
                    return res.json().then(function (body) {
                        showBanner(body.detail || explainStatus(res), "error");
                        return null;
                    });
                }
                showBanner(explainStatus(res), "error");
                return null;
            }
            return res.json();
        }).then(function (body) {
            if (!body) {
                return;
            }
            form.reset();
            showBanner("Evidence received. Staff will review it before use.", "ok");
            loadEvidence();
        });
    });

    document.getElementById("payref-form").addEventListener("submit", function (event) {
        event.preventDefault();
        var form = event.target;
        var payload = {reference: form.reference.value.trim()};
        if (form.amount.value) {
            payload.amount = form.amount.value;
        }
        if (form.paid_date.value) {
            payload.paid_date = form.paid_date.value;
        }
        if (form.note.value.trim()) {
            payload.note = form.note.value.trim();
        }
        fetch("/api/v1/portal/payment-references", {
            method: "POST",
            headers: authHeaders({"Content-Type": "application/json"}),
            body: JSON.stringify(payload)
        }).then(function (res) {
            if (!res.ok) {
                showBanner(explainStatus(res), "error");
                return null;
            }
            return res.json();
        }).then(function (body) {
            if (!body) {
                return;
            }
            form.reset();
            showBanner("Payment reference received as an unverified claim. " +
                "The business will verify it.", "ok");
            load();
        });
    });

    load();
})();
