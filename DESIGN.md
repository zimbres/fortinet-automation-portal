---
name: Fortinet Automation Portal
description: A restrained workspace for independently approved firewall operations
colors:
  primary: "#075f4b"
  ink: "#172d2a"
  muted: "#536661"
  line: "#dce4df"
  paper: "#ffffff"
  background: "#f4f7f4"
  sidebar: "#102f29"
typography:
  body:
    fontFamily: "Segoe UI, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
  heading:
    fontFamily: "Segoe UI, Arial, sans-serif"
    fontSize: "1.85rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
rounded:
  control: "6px"
  panel: "10px"
spacing:
  field: "24px"
  panel: "26px"
  page: "40px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
---

# Portal interface system

## Overview

The portal uses a restrained operations interface grounded in the approved internal workflow. The sidebar organizes requests, inventory, and configuration; the content area keeps approval and execution state separate. English copy, real records, and clear empty states are mandatory.

## Colors

Use the normative colors above: pale neutral working surfaces, a deep green navigation area, and one green action color. Semantic state colors pair with explicit text.

## Typography

Use Segoe UI with sans-serif fallbacks for product controls and Consolas only for identifiers and network values. Body is 14px; headings use a compact fixed scale.

## Layout

The desktop grid has a 248px navigation rail and a flexible workspace with 40px page padding. At 1000px the rail becomes 210px and detail columns stack. At 680px navigation becomes a horizontal strip and page padding becomes 18px.

## Elevation & Depth

Depth is expressed through surface tones and one-pixel borders. No decorative shadows.

## Shapes

Component corners are 6px for controls and 10px for panels. Status labels use 4px corners.

## Components

Statuses pair text with restrained semantic backgrounds. No animation delays task access. Visible keyboard focus, labeled inputs, a skip link, and reduced-motion support are required. No external image or font assets are needed for this task-focused interface.

## Do's and Don'ts

Keep factual status separate from approved intent. Avoid invented counters or implied success after uncertain writes. The Impeccable launcher could not run because its engine was unavailable in the sandbox. This direction was implemented directly from the approved Operate requirements; no generated concept roll or independent visual verdict is claimed.


### Transfer selection

Model multiple-choice fields use a shared Available/Selected transfer control with native highlighted rows, search, counts and four explicit arrow actions. Desktop uses two equal-width panes around a narrow action column; at 680px the panes stack and the arrows rotate vertically. Keep native field names and selected values for submission and no-JavaScript fallback. Filtering changes bulk action labels to Add all shown / Remove all shown. Required-field validation focuses the visible Available search control when no item is selected.
