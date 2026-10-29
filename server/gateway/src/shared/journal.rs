//! NET-01: an append-mostly battle journal with value semantics and a
//! constant-time clone. The gateway clones World and Session many times per
//! loop (staged transactions); a deep copy of every shot, impact and contact
//! made each clone grow with the battle (stand -11, 2026-10-29: publication
//! 1 -> 39 ms per loop, then a fail-closed lag). Reads share one buffer; the
//! first write to a shared buffer copies it (`Arc::make_mut`), so a staged
//! clone that is dropped never changes the committed one.
use std::ops::{Deref,DerefMut};
use std::sync::Arc;

pub(crate) struct Journal<T>(Arc<Vec<T>>);

impl<T> Journal<T> {
    pub(crate) fn new()->Self {Self(Arc::new(Vec::new()))}
}
impl<T> Clone for Journal<T> {
    fn clone(&self)->Self {Self(Arc::clone(&self.0))}
}
impl<T> Default for Journal<T> {
    fn default()->Self {Self::new()}
}
impl<T> Deref for Journal<T> {
    type Target=Vec<T>;
    fn deref(&self)->&Vec<T> {&self.0}
}
impl<T:Clone> DerefMut for Journal<T> {
    fn deref_mut(&mut self)->&mut Vec<T> {Arc::make_mut(&mut self.0)}
}
impl<T> From<Vec<T>> for Journal<T> {
    fn from(rows:Vec<T>)->Self {Self(Arc::new(rows))}
}
impl<T:PartialEq> PartialEq for Journal<T> {
    fn eq(&self,other:&Self)->bool {*self.0==*other.0}
}
impl<T:std::fmt::Debug> std::fmt::Debug for Journal<T> {
    fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {self.0.fmt(f)}
}
impl<'a,T> IntoIterator for &'a Journal<T> {
    type Item=&'a T;type IntoIter=std::slice::Iter<'a,T>;
    fn into_iter(self)->Self::IntoIter {self.0.iter()}
}
impl<'a,T:Clone> IntoIterator for &'a mut Journal<T> {
    type Item=&'a mut T;type IntoIter=std::slice::IterMut<'a,T>;
    fn into_iter(self)->Self::IntoIter {Arc::make_mut(&mut self.0).iter_mut()}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn net01_journal_clone_shares_and_a_write_never_reaches_the_other_copy() {
        let mut a:Journal<u32>=vec![1,2].into();let b=a.clone();
        assert!(Arc::ptr_eq(&a.0,&b.0),"clone is constant time");
        a.push(3);assert_eq!((&a[..],&b[..]),(&[1,2,3][..],&[1,2][..]));
        let mut c=b.clone();drop(b);c.push(9);assert_eq!(&c[..],&[1,2,9]);
        for x in &mut c {*x+=1;}assert_eq!(c,Journal::from(vec![2,3,10]));
        assert_eq!((&c).into_iter().count(),3);assert_eq!(format!("{:?}",c),"[2, 3, 10]");
        assert!(Journal::<u8>::default().is_empty());
    }
}
