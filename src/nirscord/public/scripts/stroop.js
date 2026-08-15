import { ws, sleep, tick, choice, cross, lock } from "./util.js";

/**
 * @type {HTMLParagraphElement}
 */
const stroop = document.querySelector("#stroop")

// The colours to display
const colours = {
    "b": "Blue",
    "g": "Green",
    "o": "Orange",
    "p": "Pink",
    "r": "Red",
    "y": "Yellow"
};

const colourKeys = Object.keys(colours);
const colourValues = Object.values(colours);

// Generate initial coloured word
stroop.style.color = choice(colourValues);
stroop.innerHTML = choice(colourValues);

document.addEventListener("keydown", lock(async ev => {
    if (!(Object.keys(colours).includes(ev.key)) || ev.repeat) return;

    // Check if the keypress matches the colour
    if (ev.key === stroop.style.color[0]) {
        ws.send("success");
    } else {
        ws.send("failure");
    }

    // zzzzzzzzzzzzz
    await sleep(500);

    // Duplicate in 1 in 4 cases
    if (Math.random() < 1 / 4) {
        stroop.style.color =  choice(colourValues).toLowerCase();
        stroop.innerHTML = stroop.style.color;

    } else {
        stroop.style.color = choice(colourValues).toLowerCase();
        stroop.innerHTML = choice(colourValues);
    }
}));
