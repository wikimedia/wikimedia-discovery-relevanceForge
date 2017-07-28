# R file to experiment with the completion suggester score

dat = read.csv("stats.csv", header=TRUE, sep=",")

library(MASS)
library(fitdistrplus)
library(logspline)

mysamp <- dat[sample(1:nrow(dat), 100000, replace=FALSE),]

fit.inc.norm <- fitdist(mysamp$incomingLinks, "norm")
fit.inc.lnorm <- fitdist(log(mysamp$incomingLinks+2), distr="norm")

fit.bytes.norm <- fitdist(mysamp$bytes, "norm")
fit.bytes.lnorm <- fitdist(log(mysamp$bytes+2), distr="norm")

fit.headings.norm <- fitdist(mysamp$headings, "norm")
fit.headings.lnorm <- fitdist(log(mysamp$headings+2), distr="norm")


fit.ext.norm <- fitdist(mysamp$externalLinks, "norm")
fit.ext.lnorm <- fitdist(log(mysamp$externalLinks+2), distr="norm")

sd(dat$incomingLinks)
sd(dat$bytes)
summary(dat$bytes)
summary(dat$headings)
plot(fit.ext.norm)
plot(fit.ext.lnorm)

plot(fit.bytes.norm)
plot(fit.bytes.lnorm)

plot(fit.headings.norm)
plot(fit.headings.lnorm)


plot(fit.norm)
plot(fit.lognorm)
plot(fit.lnorm)

pop_score <- function(maxDocs, popScore) {
  POPULARITY_MAX = 0.0004;

  if( popScore > POPULARITY_MAX ) {
    return ( 1 );
  }
  # broken log scale with maxDocs...
  # working on ratio (pv/total_project_pv) is difficult here, I was wrong :(
  pop = logb(1+(popScore*maxDocs), 1+(POPULARITY_MAX*maxDocs));
  return (pop);
}

# Score function
popqual_score <- function(maxDocs, incomingLinksRaw, externalLinksRaw, bytesRaw, headingsRaw, redirectsRaw, tmplBoost, popScore) {
  QSCORE_WEIGHT = 1;
  POPULARITY_WEIGHT = 0.4;

  SCORE_RANGE = 10000000;

  qual <- qual_score(maxDocs, incomingLinksRaw, externalLinksRaw, bytesRaw, headingsRaw, redirectsRaw, tmplBoost);
  pop <- pop_score(maxDocs, popScore);
  score = (qual * QSCORE_WEIGHT + pop * POPULARITY_WEIGHT) / (QSCORE_WEIGHT + POPULARITY_WEIGHT)

  return (score * SCORE_RANGE);
}

qual_score <- function(maxDocs, incomingLinksRaw, externalLinksRaw, bytesRaw, headingsRaw, redirectsRaw, tmplBoost) {
  INCOMING_LINKS_MAX_DOCS_FACTOR = 1/10;

  EXTERNAL_LINKS_NORM = 20;
  PAGE_SIZE_NORM = 50000;
  HEADING_NORM = 20;
  REDIRECT_NORM = 30;

  INCOMING_LINKS_WEIGHT = 0.6;
  EXTERNAL_LINKS_WEIGHT = 0.1;
  PAGE_SIZE_WEIGHT = 0.1;
  HEADING_WEIGHT = 0.2;
  REDIRECT_WEIGHT = 0.1;

#  OUTGOING_LINK_BLANCE = 2000;
#  HEADINGS_BALANCE = 3000;
#  EXT_LINKS_BALANCE = 2000;

  SCORE_RANGE = 10000000;
  # If a page gets linked by more than 1/10 of all pages.
  incLinksNorm <- maxDocs * INCOMING_LINKS_MAX_DOCS_FACTOR;

  incLinks <- scoreNormL2(incomingLinksRaw, incLinksNorm)
  pageSize <- scoreNormL2(bytesRaw, PAGE_SIZE_NORM)
  extLinks <- scoreNorm(externalLinksRaw, EXTERNAL_LINKS_NORM)
  headings <- scoreNorm(headingsRaw, HEADING_NORM)
  redirects <- scoreNorm(redirectsRaw, REDIRECT_NORM)

  score <- incLinks * INCOMING_LINKS_WEIGHT;
  score <- score + extLinks * EXTERNAL_LINKS_WEIGHT;
  score <- score + pageSize * PAGE_SIZE_WEIGHT;
  score <- score + headings * HEADING_WEIGHT;
  score <- score + redirects * REDIRECT_WEIGHT;

  score <- score / (INCOMING_LINKS_WEIGHT + EXTERNAL_LINKS_WEIGHT + PAGE_SIZE_WEIGHT + HEADING_WEIGHT + REDIRECT_WEIGHT);


  # headingsBalance <- bytesRaw / headingsRaw;
  # headingDistance <- HEADINGS_BALANCE - headingsBalance;

  # extLinksBalance <- externalLinksRaw / bytesRaw;
  # extLinksDistance <- EXT_LINKS_BALANCE - headingsBalance;

  #score <- score * (1-1/abs(headingDistance))
  #score <- score * (1-1/abs(extLinksDistance))
  score <- boost(score, tmplBoost);
  return (score);
}

# log2(value/norm + 1)
scoreNormL2 <- function(value, norm) {
  if(value > norm) {
    value <- norm;
  }
  return(log2((value/norm) +1));
}

# simple ratio
scoreNorm <- function(value, norm) {
  if(value > norm) {
    value <- norm;
  }
  return(value/norm);
}

boost <- function(score, boost) {
  if(boost > 1) {
    boost <- 1 - ( 1 / boost );
  } else {
    boost <- - ( 1 - boost );
  }
  if(boost > 0) {
    return (score + ( ( ( 1 - score ) / 2 ) * boost ))
  } else {
    return (score + ( ( score / 2 ) * boost ))
  }
}
# compute the score
dat$score <- mapply(popqual_score, nrow(dat), dat$incomingLinks, dat$externalLinks, dat$bytes, dat$headings, dat$redirects, dat$tmplBoost, dat$pop_score );
dat$score_qual <- mapply(qual_score, nrow(dat), dat$incomingLinks, dat$externalLinks, dat$bytes, dat$headings, dat$redirects, dat$tmplBoost );
dat$score_pop <- mapply(pop_score, nrow(dat), dat$pop_score );

boost(0.5, 1.5)

li <- dat[grepl("^Li", dat$page),]
oba_osa <- dat[grepl("^(Barack|Osama)", dat$page),]
peg <- dat[grepl("^Peg", dat$page),]
Po <- dat[grepl("^Po", dat$page),]
Xxx <- dat[grepl("^X", dat$page),]
Mar <- dat[grepl("^Mar", dat$page),]
M <- dat[grepl("^M", dat$page),]
Zero <- dat[grepl("^0", dat$page),]
One <- dat[grepl("^1", dat$page),]
W <- dat[grepl("^W", dat$page),]
N <- dat[grepl("^N", dat$page),]
I <- dat[grepl("^I", dat$page),]
obama <- dat[grepl("^(Barack Oba|Obama)", dat$page),]

J <- dat[grepl("^J", dat$page),]

White <- dat[grepl("^White", dat$page),]

bug <- dat[dat$score_qual > 1,]


# various stuff to explore distribution

#quantile(dat$redirects, 0.999);

summary(dat$score_pop)
summary(dat$score_qual)

#plot(density(dat$incomingLinks, from=0.00001), log="x", xlim=c(1,max(dat$incomingLinks)))
#plot(density(dat$externalLinks, from=0.00001), log="x", xlim=c(1,max(dat$externalLinks)))
#plot(density(dat$bytes, from=0.00001), log="x", xlim=c(1,max(dat$bytes)))
#plot(density(dat$headings, from=0.00001), log="x", xlim=c(1,max(dat$headings)))
#plot(density(dat$redirects, from=0.00001), log="x", xlim=c(1,max(dat$redirects)))

#plot(density(dat$incomingLinks, from=0.00001), log="x", xlim=c(1,max(dat$incomingLinks)))

mysamp <- dat[sample(1:nrow(dat), 100000, replace=FALSE),]

#plot(mysamp$incomingLinks+10, mysamp$score, log="x", cex=0.2)
#plot(mysamp$bytes+10, mysamp$score, log="x", cex=0.2)
#plot(mysamp$headings, mysamp$score, cex=0.2)
#plot(mysamp$redirects, mysamp$score, cex=0.2)
#plot(mysamp$externalLinks+10, mysamp$score,  cex=0.2)



#plot(density(dat$score, from=0.00001), log="x", xlim=c(1,max(dat$score)))


#plot(density(dat$headingBalance))
#plot(density(dat$headings))
#plot(dat$incomingLinks + 10,dat$externalLinks + 10, log="yx", cex=0.2)
#plot(dat$incomingLinks + 10, dat$bytes + 10, log="yx", cex=0.2)
#plot(dat$incomingLinks + 10, dat$headings + 10, log="yx", cex=0.2)
#plot(dat$incomingLinks + 10, dat$headings + 10, log="yx", cex=0.2)
#plot(dat$incomingLinks + 10, dat$redirects + 10, log="yx", cex=0.2)
plot(mysamp$score_pop, mysamp$score, cex=0.2)
plot(mysamp$score_qual, mysamp$score, cex=0.2)

