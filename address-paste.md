# Pasting an address

Plain-language guide for CBM staff and mentors. (Build detail lives in
`CLAUDE.md` and `prds/address-paste-parsing-plan.md`.)

## What it does

When you find an address somewhere else — a company's website, an email
signature, a Google Maps listing — you no longer have to retype it field by
field. **Copy the whole address, paste it into the first address box, and the
rest of the boxes fill themselves in.**

Pasting `1234 Main St Suite 200, Cleveland, OH 44113` into the street box gives
you:

| Box | Filled with |
|---|---|
| Address line 1 | 1234 Main St |
| Address line 2 | Suite 200 |
| City | Cleveland |
| State | OH |
| ZIP | 44113 |

It copes with the usual variations: the address on one line or several, a
company name in front of it (`Acme Widgets, 1234 Main St, …`), a spelled-out
state (`Ohio` becomes `OH`), a ZIP+4, a PO box, a suite or apartment number, and
a stray phone number or web address pasted along with it.

## You can always undo it

Right below the address you'll see a line saying what changed — *"Filled City,
State and ZIP from what you pasted"* — with an **Undo** link. Undo puts every
box back exactly as it was, including anything the paste replaced. The boxes
that changed also flash briefly so you can see what moved.

Nothing is saved until you save the record, so you can also just correct a box
by hand.

## Where it works

- **Client, Partner and Funder Management** — the Details tab, on the contact
  address and on the company's billing and shipping addresses
- **Mentor Administration** and **My Mentor Profile**
- **Workspace Directories** — the edit window
- **The volunteer and client intake forms** on the public site

## What it won't do

- **It won't check the address is real.** It splits up what you paste; it
  doesn't verify the street exists or correct spelling.
- **It leaves ordinary typing alone.** Typing a street address normally never
  triggers it — it only acts on something that clearly looks like a full or
  partial address.
- **US addresses only.** Paste an overseas address and it stays exactly as you
  pasted it, for you to sort into the boxes yourself.

Two forms work slightly differently because they have fewer boxes. The
**volunteer form** has no City or State field, so the city and state stay in the
Street box rather than being thrown away. The **client intake form** has only a
Zip Code box, so pasting a full address there keeps just the ZIP — which is an
improvement, because that box used to chop a pasted address down to its first
ten characters.
