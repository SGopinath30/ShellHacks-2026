/** Test-only cases; never imported by the public demo. */
import { projects } from "./fixtures";
import type { Project } from "./types";
export const completeA: Project = {
  ...projects[0],
  constructionStart: "2027-01-01",
  constructionEnd: "2027-01-11",
};
export const completeB: Project = {
  ...projects[1],
  constructionStart: "2027-01-06",
  constructionEnd: "2027-01-16",
};
export const scheduleCases = [
  { name: "complete", project: completeB, status: "valid", overlap: 5 },
  {
    name: "touching",
    project: {
      ...completeB,
      constructionStart: "2027-01-11",
      constructionEnd: "2027-01-20",
    },
    status: "valid",
    overlap: 0,
  },
  {
    name: "disjoint",
    project: {
      ...completeB,
      constructionStart: "2027-02-01",
      constructionEnd: "2027-02-11",
    },
    status: "valid",
    overlap: 0,
  },
  {
    name: "start-only",
    project: { ...completeB, constructionEnd: null },
    status: "incomplete",
    overlap: null,
  },
  {
    name: "end-only",
    project: { ...completeB, constructionStart: null },
    status: "incomplete",
    overlap: null,
  },
  {
    name: "neither",
    project: {
      ...completeB,
      constructionStart: null,
      constructionEnd: null,
      inServiceDate: null,
    },
    status: "incomplete",
    overlap: null,
  },
  {
    name: "milestone-only",
    project: {
      ...completeB,
      constructionStart: null,
      constructionEnd: null,
      inServiceDate: "2027-01-10",
    },
    status: "incomplete",
    overlap: null,
  },
  {
    name: "reversed",
    project: { ...completeB, constructionStart: "2027-01-17" },
    status: "invalid",
    overlap: null,
  },
  {
    name: "equal",
    project: { ...completeB, constructionStart: "2027-01-16" },
    status: "invalid",
    overlap: null,
  },
  {
    name: "impossible",
    project: { ...completeB, constructionStart: "2027-02-30" },
    status: "invalid",
    overlap: null,
  },
  {
    name: "malformed",
    project: {
      ...completeB,
      constructionStart: "not-a-date",
      constructionEnd: null,
      inServiceDate: "2027-02-30",
    },
    status: "invalid",
    overlap: null,
  },
];
