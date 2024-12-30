import repl from "repl";
import { LunchMoney } from "lunch-money";

// TODO can we add helper methds for debugging in the future?
// https://stackoverflow.com/questions/31173473/list-all-global-variables-in-node-js

const local = repl.start("> ");
const lunchMoney = new LunchMoney({
  token: process.env.LUNCH_MONEY_API_KEY || "",
});

local.context.lunchMoney = lunchMoney;
