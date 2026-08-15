import { choice, cross, loop, Results, sleep, tick } from "./util.js"

const alphabet = [..."abcdefghijklmnopqrstuvwxyz"];

const nBack = document.querySelector("#n-back");
const marker = document.querySelector("#marker");

let isSpace = false;
let tracker = Array(3);

document.addEventListener("keydown", async ev => {
    if (ev.key !== " " || isSpace || ev.repeat) return;

    // Set the keypress
    isSpace = true;

    // Check if the current letter is 2-back
    if (tracker.at(0) === tracker.at(-1)) {
        ws.send(Results.TARGET_SUCCESS);
    } else {
        ws.send(Results.NON_TARGET_FAILURE);
    }
});

loop(async () => {
    const prev = tracker.shift();

    // Duplicate in 1 in 4 cases
    if (Math.random() < 1 / 4) {
        nBack.innerHTML = tracker[0];
        tracker.push(tracker[0]);

    } else {
        const letter = choice(alphabet);
        nBack.innerHTML = letter;
        tracker.push(letter);
    }

    // Give the user time to react
    await sleep(2000);

    // Forward non-target results
    if (!isSpace) {
            
        if (tracker.at(0) === tracker.at(-1)) {
            ws.send(Results.TARGET_FAILURE);
    
        } else {
            ws.send(Results.NON_TARGET_SUCCESS);
        }
    }

    // Reset the keypress
    isSpace = false;
});
